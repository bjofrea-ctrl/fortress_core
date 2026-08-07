import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from app.core.indicators import calculate_all_indicators
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.probabilistic_engine import BayesianOnlineUpdater


class SignalEngine:
    def __init__(self, regime_classifier: GlobalRegimeClassifier,
                 bayesian_updater: Optional[BayesianOnlineUpdater] = None):
        self.regime_classifier = regime_classifier
        self.bayesian_updater = bayesian_updater
        # Priors: usados como base_weight del posterior Bayesiano y como
        # fallback mientras no haya evidencia suficiente para ese (régimen, factor)
        self.factor_weights = {
            0: {"momentum": 0.35, "technical": 0.65},
            1: {"momentum": 0.30, "technical": 0.70},
            2: {"momentum": 0.20, "technical": 0.80},
            3: {"momentum": 0.10, "technical": 0.90},
        }

    def _get_factor_weights(self, regime_state: int) -> Dict[str, float]:
        priors = self.factor_weights.get(regime_state, self.factor_weights[0])
        if self.bayesian_updater is None:
            return priors

        raw = {}
        for factor, prior_w in priors.items():
            signal_name = f"{regime_state}_{factor}"
            raw[factor] = self.bayesian_updater.get_weight(signal_name, default=prior_w)

        total = sum(raw.values())
        if total <= 0:
            return priors
        return {f: w / total for f, w in raw.items()}

    def _normalize(self, value, lo, hi) -> float:
        return float(np.clip((value - lo) / (hi - lo), 0, 1))

    def _factor_scores(self, stock_data: pd.DataFrame) -> Dict[str, float]:
        """
        Cada componente contribuye siempre (favorable o no) en vez de sumar
        sólo cuando es favorable. La asimetría anterior (sumar 1.0 sólo si la
        tendencia estaba confirmada, sin penalizar cuando no) sesgaba el score
        hacia arriba sin castigar el caso contrario — ver walk-forward IC.
        """
        latest = stock_data.iloc[-1]
        mom = latest.get("momentum_12_1")
        momentum_score = self._normalize(mom, -50, 100) if pd.notna(mom) else 0.5

        tech = [1.0 if latest.close > latest.ema50 > latest.ema200 else 0.0]

        rsi_v = latest.get("rsi14")
        if pd.notna(rsi_v):
            tech.append(0.8 if 45 < rsi_v < 70 else 0.4)

        adx_v = latest.get("adx14")
        if pd.notna(adx_v):
            tech.append(0.9 if adx_v > 25 else 0.3)

        technical_score = np.mean(tech)
        return {"momentum": momentum_score, "technical": technical_score}

    def compute_score_series(self, indicators_df: pd.DataFrame, regime_state: int = 0) -> pd.Series:
        """
        Reproduce _factor_scores de forma vectorizada para toda la serie
        (no sólo el último día). Se usa para diagnóstico walk-forward de la
        calidad predictiva del score compuesto, independiente del filtro BUY.
        """
        mom = indicators_df.get("momentum_12_1", pd.Series(np.nan, index=indicators_df.index))
        momentum_score = ((mom + 50) / 150).clip(0, 1)
        momentum_score = momentum_score.where(mom.notna(), 0.5)

        trend_up = (indicators_df["close"] > indicators_df["ema50"]) & (indicators_df["ema50"] > indicators_df["ema200"])
        trend_component = pd.Series(np.where(trend_up, 1.0, 0.0), index=indicators_df.index)

        rsi = indicators_df.get("rsi14", pd.Series(np.nan, index=indicators_df.index))
        rsi_component = pd.Series(np.where(rsi.notna(), np.where(rsi.between(45, 70, inclusive="neither"), 0.8, 0.4), np.nan),
                                   index=indicators_df.index)

        adx = indicators_df.get("adx14", pd.Series(np.nan, index=indicators_df.index))
        adx_component = pd.Series(np.where(adx.notna(), np.where(adx > 25, 0.9, 0.3), np.nan), index=indicators_df.index)

        tech_df = pd.concat([trend_component, rsi_component, adx_component], axis=1)
        technical_score = tech_df.mean(axis=1, skipna=True)

        weights = self._get_factor_weights(regime_state)
        return momentum_score * weights["momentum"] + technical_score * weights["technical"]

    def compute_factor_frame(self, indicators_df: pd.DataFrame) -> pd.DataFrame:
        """
        Componentes de factor individuales (no combinados) + máscara de
        elegibilidad reproduciendo los filtros duros de generate_signal.
        Para diagnóstico de IC por factor dentro de la población de días
        que realmente serían candidatos a señal, no en todos los días.
        """
        df = indicators_df
        mom = df.get("momentum_12_1", pd.Series(np.nan, index=df.index))
        momentum = ((mom + 50) / 150).clip(0, 1)

        trend_ok = (df["close"] > df["ema50"]) & (df["ema50"] > df["ema200"])
        trend = pd.Series(np.where(trend_ok, 1.0, 0.0), index=df.index)

        rsi = df.get("rsi14", pd.Series(np.nan, index=df.index))
        rsi_score = pd.Series(np.where(rsi.between(45, 70, inclusive="neither"), 0.8, 0.4), index=df.index)
        rsi_score = rsi_score.where(rsi.notna())

        adx = df.get("adx14", pd.Series(np.nan, index=df.index))
        adx_score = pd.Series(np.where(adx > 25, 0.9, 0.3), index=df.index)
        adx_score = adx_score.where(adx.notna())

        vol_ratio = df.get("volume_ratio", pd.Series(np.nan, index=df.index))
        eligible = trend_ok & (adx >= 20) & (rsi > 40) & (rsi < 75) & (vol_ratio >= 1.0)

        return pd.DataFrame({
            "momentum": momentum, "trend": trend, "rsi": rsi_score, "adx": adx_score,
            "eligible": eligible.fillna(False), "close": df["close"],
        }, index=df.index)

    def generate_signal(self, stock_data: pd.DataFrame, symbol: str, regime_state: int) -> Optional[Dict]:
        if len(stock_data) < 200 or regime_state == 3:
            return None

        stock_data = calculate_all_indicators(stock_data)
        if len(stock_data) == 0:
            return None
        latest = stock_data.iloc[-1]
        scores = self._factor_scores(stock_data)
        weights = self._get_factor_weights(regime_state)
        overall = sum(scores[f] * weights[f] for f in weights)

        if not (latest.close > latest.ema50 > latest.ema200):
            return None
        if latest.get("adx14", 0) < 20:
            return None
        if not (40 < latest.get("rsi14", 50) < 75):
            return None
        if latest.get("volume_ratio", 1) < 1.0:
            return None
        if overall < 0.6:
            return None

        atr_v = latest.atr14
        entry = latest.close
        stop_loss = entry - 2.0 * atr_v
        take_profit = entry + 4.0 * atr_v
        risk = entry - stop_loss
        payoff_ratio = (take_profit - entry) / risk if risk > 0 else 0.0
        return {
            "symbol": symbol,
            "date": stock_data.index[-1],
            "signal_type": "BUY",
            "score": float(overall),
            "entry_price": float(entry),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "payoff_ratio": float(payoff_ratio),
            "regime_state": regime_state,
            "factors": scores,
            "atr": float(atr_v),
        }

    def rank_signals(self, signals: List[Dict]) -> List[Dict]:
        return sorted(signals, key=lambda x: x["score"], reverse=True)

    def filter_by_regime_exposure(self, signals: List[Dict], regime_state: int, current_exposure: float) -> List[Dict]:
        max_exposure = self.regime_classifier.REGIME_ALLOCATION[regime_state]["equity"]
        if current_exposure >= max_exposure:
            return []
        max_new = int((max_exposure - current_exposure) / 0.10)
        return signals[:max_new]