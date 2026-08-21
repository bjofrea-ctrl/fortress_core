from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.indicators import calculate_all_indicators
from app.core.probabilistic_engine import BayesianOnlineUpdater
from app.core.regime_classifier import GlobalRegimeClassifier

# Puerta de riesgo/recompensa mínimo para una señal con resolución estructural
# (T1.4, PLAN_INTEGRACION_INDICAGENT.md): el VALOR 1.5 es el default del ticket y
# NO está validado empíricamente — la comparación A/B que lo valida/ajusta vive en
# `scripts/compare_structural_stop.py` + `RESUMEN_STOP_ESTRUCTURAL.md`.
# Con el fallback de ATR puro (market_structure=None) RR es siempre exactamente
# 4/2 = 2.0 ≥ 1.5, así que la puerta es transparente sobre el baseline.
MIN_RR = 1.5


def _resolve_stop(entry: float, atr_v: float, market_structure: Optional[Dict]) -> float:
    """Jerarquía de stop estructural, adaptada del trade_framer.py de indicAgent.

    Primer match gana; fallback a 2×ATR si nada estructural aplica. Con
    ``market_structure=None`` el resultado es OBLIGATORIAMENTE el fallback de
    siempre (entry − 2·ATR) — regresión asegurada por tests.
    """
    if market_structure:
        ob = market_structure.get("order_block") or {}
        if (ob.get("ob_type") == 1
                and not ob.get("ob_mitigated", True)
                and np.isfinite(ob.get("ob_bottom", np.nan))
                and ob["ob_bottom"] < entry):
            return ob["ob_bottom"] - atr_v * 0.20

        sweep = market_structure.get("liquidity_sweep") or {}
        if (sweep.get("sweep_type") == 1
                and sweep.get("sweep_detected")
                and np.isfinite(sweep.get("sweep_level", np.nan))
                and sweep["sweep_level"] < entry):
            return sweep["sweep_level"] - atr_v * 0.30

        swing_low = market_structure.get("nearest_swing_low")
        if swing_low is not None and np.isfinite(swing_low) and swing_low < entry:
            return swing_low - atr_v * 0.25

    return entry - 2.0 * atr_v  # fallback del baseline, sin cambios


def _resolve_target(entry: float, atr_v: float, market_structure: Optional[Dict]) -> float:
    """Candidatos de target por encima de entry; gana el MÁS CERCANO (RR
    mínimo realista, no el más optimista). Fallback 4×ATR. Con
    ``market_structure=None`` devuelve obligatoriamente entry + 4·ATR."""
    if market_structure:
        candidates = []
        fvg = market_structure.get("fair_value_gap") or {}
        if (fvg.get("fvg_type") == 1
                and np.isfinite(fvg.get("fvg_bottom", np.nan))
                and fvg["fvg_bottom"] > entry):
            candidates.append(fvg["fvg_bottom"])
        resistance = market_structure.get("nearest_resistance")
        if resistance is not None and np.isfinite(resistance) and resistance > entry:
            candidates.append(resistance)
        if candidates:
            return min(candidates)

    return entry + 4.0 * atr_v  # fallback del baseline, sin cambios


class SignalEngine:
    def __init__(self, regime_classifier: GlobalRegimeClassifier,
                 bayesian_updater: Optional[BayesianOnlineUpdater] = None):
        self.regime_classifier = regime_classifier
        self.bayesian_updater = bayesian_updater
        # Priors derivados de diagnose_factor_ic (pooled 2019-2024, SPY/QQQ/
        # AAPL/MSFT/GOOGL/AMZN/NVDA, sólo días elegibles): momentum IC=0.064,
        # rsi IC=0.032 -> peso proporcional a |IC|. trend y adx quedaron
        # afuera del score ponderado porque trend es constante dentro de la
        # población elegible (no discrimina) y adx no resiste la corrección
        # de comparaciones múltiples: IC +0.0679 (t=+2.31) nominal intra-día
        # con Newey-West (§0.5a, rr2_intraday_20260811_150741.txt) — marginal,
        # no robusto bajo Bonferroni-4 (umbral ≈2.5). Ambos siguen
        # como gates duros en generate_signal, sólo salieron del promedio.
        # No hay evidencia por-régimen todavía; el mismo prior se usa en los
        # 4 regímenes y el BayesianOnlineUpdater lo refina online con el
        # régimen real de cada fecha a medida que cierran trades.
        _momentum_ic, _rsi_ic = 0.0637, 0.0322
        _mom_w = _momentum_ic / (_momentum_ic + _rsi_ic)
        self.factor_weights = {
            regime: {"momentum": round(_mom_w, 4), "rsi": round(1 - _mom_w, 4)}
            for regime in (0, 1, 2, 3)
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
        Sólo momentum y rsi entran al score ponderado: son los únicos factores
        con IC positivo confirmado dentro de la población que pasa el filtro
        duro de entrada (ver diagnose_factor_ic). trend y adx quedaron
        afuera del promedio -siguen actuando como gates en generate_signal-
        porque trend es constante entre los días elegibles (no discrimina) y
        adx no resiste la corrección de comparaciones múltiples (IC +0.0679,
        t=+2.31 nominal intra-día con Newey-West — §0.5a — marginal, no
        robusto bajo Bonferroni-4 ≈2.5).
        """
        latest = stock_data.iloc[-1]
        mom = latest.get("momentum_12_1")
        momentum_score = self._normalize(mom, -50, 100) if pd.notna(mom) else 0.5

        rsi_v = latest.get("rsi14")
        rsi_score = (0.8 if 45 < rsi_v < 70 else 0.4) if pd.notna(rsi_v) else 0.5

        return {"momentum": momentum_score, "rsi": rsi_score}

    def compute_score_series(self, indicators_df: pd.DataFrame, regime_state: int = 0) -> pd.Series:
        """
        Reproduce _factor_scores de forma vectorizada para toda la serie
        (no sólo el último día). Se usa para diagnóstico walk-forward de la
        calidad predictiva del score compuesto, independiente del filtro BUY.
        """
        mom = indicators_df.get("momentum_12_1", pd.Series(np.nan, index=indicators_df.index))
        momentum_score = ((mom + 50) / 150).clip(0, 1)
        momentum_score = momentum_score.where(mom.notna(), 0.5)

        rsi = indicators_df.get("rsi14", pd.Series(np.nan, index=indicators_df.index))
        rsi_score = pd.Series(np.where(rsi.between(45, 70, inclusive="neither"), 0.8, 0.4), index=indicators_df.index)
        rsi_score = rsi_score.where(rsi.notna(), 0.5)

        weights = self._get_factor_weights(regime_state)
        return momentum_score * weights["momentum"] + rsi_score * weights["rsi"]

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

    def generate_signal(self, stock_data: pd.DataFrame, symbol: str, regime_state: int,
                        market_structure: Optional[Dict] = None) -> Optional[Dict]:
        """Genera señal BUY para la última barra.

        T1.4 (PLAN_INTEGRACION_INDICAGENT.md): con ``market_structure=None`` el
        comportamiento es IDÉNTICO al anterior (stop = entry − 2·ATR, target =
        entry + 4·ATR, puerta RR transparente porque RR=2.0 ≥ MIN_RR exacto).
        Con dict de estructura (vía ``market_structure_history`` — causal, solo
        datos ≤ fecha de decisión): jerarquía estructural para stop/target
        (order block → sweep → último swing low; FVG/resistencia para target)
        y puerta de RR mínimo: si el mejor target estructural deja RR < MIN_RR,
        NO se genera la señal (devuelve None).

        Alcance declarado: los niveles estructurales resuelven el stop/target
        REPORTADO de la señal (y el payoff que alimenta el sizing Kelly);
        la ejecución de salidas sigue siendo la mecánica de régimen de
        ``adaptive_risk.check_all_stops`` (orden de prioridad intacto →
        ``barrier_labeling.verify_fidelity`` no se ve afectada; ver
        RESUMEN_STOP_ESTRUCTURAL.md).
        """
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
        stop_loss = _resolve_stop(entry, atr_v, market_structure)
        take_profit = _resolve_target(entry, atr_v, market_structure)
        risk = entry - stop_loss
        if risk <= 0:
            return None  # nivel estructural por encima del entry: no viable
        reward = take_profit - entry
        if reward <= 0 or reward / risk < MIN_RR:
            return None  # puerta RR mínima (trade_framer de indicAgent)
        payoff_ratio = reward / risk
        return {
            "symbol": symbol,
            "date": stock_data.index[-1],
            "signal_type": "BUY",
            "score": float(overall),
            "entry_price": float(entry),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "payoff_ratio": float(payoff_ratio),
            "structural_resolution": market_structure is not None,
            "regime_state": regime_state,
            "factors": scores,
            "atr": float(atr_v),
            "indicators": {
                "close": float(latest.close),
                "ema50": float(latest.ema50),
                "ema200": float(latest.ema200),
                "adx14": float(latest.get("adx14", np.nan)),
                "rsi14": float(latest.get("rsi14", np.nan)),
                "volume_ratio": float(latest.get("volume_ratio", np.nan)),
            },
        }

    def _fixed_score_series(self, indicators_df: pd.DataFrame) -> pd.Series:
        """Score técnico con pesos FIJOS (factor_weights[0], sin BMA online)
        para toda la serie. Comparte definición con compute_g2_rank_scores."""
        mom = indicators_df.get("momentum_12_1", pd.Series(np.nan, index=indicators_df.index))
        momentum_score = ((mom + 50) / 150).clip(0, 1).where(mom.notna(), 0.5)

        rsi = indicators_df.get("rsi14", pd.Series(np.nan, index=indicators_df.index))
        rsi_score = pd.Series(
            np.where(rsi.between(45, 70, inclusive="neither"), 0.8, 0.4),
            index=indicators_df.index,
        ).where(rsi.notna(), 0.5)

        priors = self.factor_weights[0]
        return momentum_score * priors["momentum"] + rsi_score * priors["rsi"]

    @staticmethod
    def _rolling_rank01(s: pd.Series, window: int = 260, min_periods: int = 60) -> pd.Series:
        """Percentil rolling causal en [-1,1]: rank del valor actual dentro de
        la ventana de días anteriores (inclusive). Sin lookahead. Misma
        definición que la usada en el diagnóstico H7-OOS."""
        def _pct(w):
            return 2.0 * (w <= w[-1]).mean() - 1.0

        return s.rolling(window, min_periods=min_periods).apply(_pct, raw=True).fillna(0.0)

    def compute_g2_rank_scores(self, indicators_df: pd.DataFrame,
                               sentiment_data: Dict = None) -> pd.Series:
        """
        Señal G2 de la prueba de bloques H7-OOS (blend 0.50 sobre rankings
        causales en [-1,1]) de forma vectorizada para toda la serie:

            G2 = 0.5 * rank(score_técnico) + 0.5 * s_v1
            s_v1 = -rank(aaii_bullbear_spread)

        - score_técnico con pesos FIJOS (factor_weights[0], sin BMA online):
          una serie histórica recomputada con pesos actuales contaminaría el
          ranking con información futura. El gate de entrada del backtest
          sigue usando el score real (con BMA) vía generate_signal — aquí
          sólo se construye la señal de RANKING que H7 validó.
        - sentiment_data: dict {fecha: spread crudo AAII} (anti-lookahead
          ya resuelto por el caller). Sin dato -> s_v1 = 0 (neutro), igual
          que el motor degrada a baseline.
        - rank_score y s_v1 sin datos (warmup < 60 obs) quedan en 0.0.
        """
        g2 = 0.5 * self._rolling_rank01(self._fixed_score_series(indicators_df))

        if sentiment_data:
            spread = pd.Series(sentiment_data, dtype=float).reindex(indicators_df.index)
            g2 = g2 + 0.5 * (-self._rolling_rank01(spread))

        return g2.clip(-1.0, 1.0)

    def compute_g3_rank_scores(self, indicators_df: pd.DataFrame,
                               fundamental_series: pd.Series = None) -> pd.Series:
        """
        Señal G3 del trial 0b-v2-fund (Fase 1, categoría fundamental):

            G3 = 0.5 * rank(score_técnico fijo) + 0.5 * rank(score_fundamental)

        - score_fundamental: serie diaria point-in-time del blend de los
          14 ratios del motor (compute_fundamental_score_series), sin
          lookahead (fecha de filing real).
        - Sin cobertura fundamental -> componente 0.0 (neutro), igual que
          G2 sin AAII; los símbolos sin panel se rankean por score puro.
        - Ranking causal 260d (misma definición que H7-OOS).
        """
        g3 = 0.5 * self._rolling_rank01(self._fixed_score_series(indicators_df))
        if fundamental_series is not None:
            f = fundamental_series.reindex(indicators_df.index).ffill().fillna(0.0)
            g3 = g3 + 0.5 * self._rolling_rank01(f)
        return g3.clip(-1.0, 1.0)

    def rank_signals(self, signals: List[Dict]) -> List[Dict]:
        # Con g3_score presente, el ranking usa la señal de ranking H7
        # (blend 0.50 sobre rankings); sin ella, g2_score; sin ambas, el
        # score técnico puro (backward-compatible).
        return sorted(signals, key=lambda x: x.get("g3_score", x.get("g2_score", x["score"])), reverse=True)

    def filter_by_regime_exposure(self, signals: List[Dict], regime_state: int, current_exposure: float) -> List[Dict]:
        max_exposure = self.regime_classifier.REGIME_ALLOCATION[regime_state]["equity"]
        if current_exposure >= max_exposure:
            return []
        max_new = int((max_exposure - current_exposure) / 0.10)
        return signals[:max_new]
