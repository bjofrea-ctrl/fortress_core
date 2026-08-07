import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from app.core.indicators import calculate_all_indicators
from app.core.regime_classifier import GlobalRegimeClassifier


class SignalEngine:
    def __init__(self, regime_classifier: GlobalRegimeClassifier):
        self.regime_classifier = regime_classifier
        self.factor_weights = {
            0: {"momentum": 0.35, "technical": 0.65},
            1: {"momentum": 0.30, "technical": 0.70},
            2: {"momentum": 0.20, "technical": 0.80},
            3: {"momentum": 0.10, "technical": 0.90},
        }

    def _normalize(self, value, lo, hi) -> float:
        return float(np.clip((value - lo) / (hi - lo), 0, 1))

    def _factor_scores(self, stock_data: pd.DataFrame) -> Dict[str, float]:
        latest = stock_data.iloc[-1]
        mom = latest.get("momentum_12_1")
        momentum_score = self._normalize(mom, -50, 100) if pd.notna(mom) else 0.5

        tech = []
        if latest.close > latest.ema50 > latest.ema200:
            tech.append(1.0)

        rsi_v = latest.get("rsi14")
        if pd.notna(rsi_v):
            tech.append(0.8 if 45 < rsi_v < 70 else 0.4)

        adx_v = latest.get("adx14")
        if pd.notna(adx_v):
            tech.append(0.9 if adx_v > 25 else 0.3)

        technical_score = np.mean(tech) if tech else 0.5
        return {"momentum": momentum_score, "technical": technical_score}

    def generate_signal(self, stock_data: pd.DataFrame, symbol: str, regime_state: int) -> Optional[Dict]:
        if len(stock_data) < 200 or regime_state == 3:
            return None

        stock_data = calculate_all_indicators(stock_data)
        if len(stock_data) == 0:
            return None
        latest = stock_data.iloc[-1]
        scores = self._factor_scores(stock_data)
        weights = self.factor_weights.get(regime_state, self.factor_weights[0])
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