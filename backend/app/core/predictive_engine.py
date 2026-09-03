"""
Motor de Análisis Predictivo Fortress Core — Fase 2

Integra:
- 15 indicadores técnicos con respaldo académico
- 15 indicadores fundamentales (cuando disponibles)
- Correlaciones macro (DXY, oro, plata, bonos, commodities)
- Señales de mercados de predicción (Polymarket-like)
- Detección de manipulación institucional
- Pesos adaptativos según régimen de mercado
- Probabilidades calibradas por horizonte temporal

Referencias académicas:
- Jegadeesh & Titman (1993): Momentum
- Brock, Lakonishok & LeBaron (1992): Medias móviles
- Fama & French (1992): Value factors
- Novy-Marx (2013): Gross profitability
- Bernard & Thomas (1989): PEAD/SUE
- Amihud (2002): Iliquidez
- Wolfers & Zitzewitz (2004): Mercados de predicción
- Goldstein & Guembel (2008): Manipulación
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.advanced_agents import NvidiaNIMClient
from app.core.predictive_indicators import (
    MACRO_CORRELATIONS,
    calculate_predictive_indicators,
    compute_gold_silver_ratio,
)
from app.core.sentiment_regime import (
    AAII_SPREAD_BOUND,
    ER_FAST,
    ER_SLOW,
    SENTIMENT_EXTREME,
    SENTIMENT_REGIME_DOMINANCE,
)
from app.core.triad_agents import TriadConsensus, TriadEvaluator

# ============================================================
# Configuración de pesos según régimen de mercado
# ============================================================

REGIME_WEIGHTS: Dict[int, Dict[str, float]] = {
    # 0: Crecimiento normal (bull)
    0: {
        "technical_momentum": 0.35,
        "technical_reversion": 0.10,
        "fundamental_value": 0.15,
        "fundamental_growth": 0.15,
        "macro": 0.10,
        "sentiment_manipulation": 0.10,
        "volatility_liquidity": 0.05,
    },
    # 1: Riesgo elevado (bear)
    1: {
        "technical_momentum": 0.15,
        "technical_reversion": 0.20,
        "fundamental_value": 0.25,
        "fundamental_growth": 0.10,
        "macro": 0.15,
        "sentiment_manipulation": 0.10,
        "volatility_liquidity": 0.05,
    },
    # 2: Rango lateral
    2: {
        "technical_momentum": 0.20,
        "technical_reversion": 0.30,
        "fundamental_value": 0.15,
        "fundamental_growth": 0.10,
        "macro": 0.10,
        "sentiment_manipulation": 0.10,
        "volatility_liquidity": 0.05,
    },
    # 3: Turbulento/crisis
    3: {
        "technical_momentum": 0.10,
        "technical_reversion": 0.15,
        "fundamental_value": 0.20,
        "fundamental_growth": 0.05,
        "macro": 0.25,
        "sentiment_manipulation": 0.10,
        "volatility_liquidity": 0.15,
    },
}

# Pesos por horizonte temporal
HORIZON_WEIGHTS: Dict[str, Dict[str, float]] = {
    "short_term_1_30d": {
        "technical_reversion": 0.40,
        "volatility_liquidity": 0.25,
        "sentiment_manipulation": 0.20,
        "technical_momentum": 0.15,
    },
    "medium_term_1_6m": {
        "technical_momentum": 0.30,
        "technical_reversion": 0.15,
        "macro": 0.20,
        "fundamental_growth": 0.15,
        "sentiment_manipulation": 0.10,
        "volatility_liquidity": 0.10,
    },
    "long_term_1_5y": {
        "fundamental_value": 0.45,
        "macro": 0.25,
        "technical_momentum": 0.15,
        "sentiment_manipulation": 0.05,
        "technical_reversion": 0.05,
        "fundamental_growth": 0.05,
    },
}

# Umbrales de decisión
DECISION_THRESHOLDS = [
    ("COMPRAR_FUERTE", 0.55),
    ("COMPRAR", 0.30),
    ("MANTENER", -0.10),
    ("VENDER/REDUCIR", -0.30),
    ("VENDER_FUERTE", -1.01),
]


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class SignalDetail:
    name: str
    category: str
    value: float
    signal: float  # -1 a +1
    weight: float
    explanation: str


@dataclass
class PredictionResult:
    symbol: str
    timestamp: str
    regime_state: int
    regime_name: str

    # Scores por categoría
    technical_score: float = 0.0
    fundamental_score: float = 0.0
    macro_score: float = 0.0
    sentiment_score: float = 0.0
    volatility_score: float = 0.0

    # Score compuesto y decisión
    composite_score: float = 0.0
    decision: str = "MANTENER"
    confidence: str = "Baja"   # categórico ("Baja"/"Media"/"Alta") — NO probabilidad calibrada

    # ── HONESTIDAD DEL MOTOR (AUDITORIA_NIVEL_DIOS_20260902 F0.2) ────────────
    # Este motor es HEURÍSTICO: combina indicadores técnicos + fundamentales
    # + macro + sentiment + TRIAD (BULL/BEAR/CONTRARIAN vía LLM) con pesos fijos
    # por régimen. NO pasó por trial pre-registrado, NO tiene DSR medido,
    # NO consume slot del ledger, NO está validado contra OOS walk-forward.
    # Comparación con signal_engine.py: el `SignalEngine` genera señales que
    # SÍ pasan por el ledger `motor_signal` con DSR≥0.90 — `signal_diagnosis`
    # para diagnósticos. Este motor NO está en ese circuito.
    motor: str = "heuristico_no_validado"   # único valor posible mientras no se valide
    probabilidades_calibradas: bool = False  # False: las prob_up_* son scores
                                              # normalizados a [0,1], NO frecuencias
                                              # empíricas. No usar como P(real).
    # ───────────────────────────────────────────────────────────────────────

    # Probabilidades por horizonte
    prob_up_short: float = 0.5
    prob_up_medium: float = 0.5
    prob_up_long: float = 0.5

    # Detalles
    signals: List[SignalDetail] = field(default_factory=list)

    # Metadatos
    manipulation_risk: float = 0.0
    manipulation_signals: List[str] = field(default_factory=list)

    # TRIAD consensus
    triad_consensus: Optional[TriadConsensus] = None
    triad_score: float = 0.0
    triad_recommendation: str = "MANTENER"
    triad_agreement: str = "DIVERGENTE"


# ============================================================
# Motor predictivo principal
# ============================================================

class PredictiveEngine:
    def __init__(self, regime_classifier=None):
        self.regime_classifier = regime_classifier
        self.nim_client = NvidiaNIMClient()
        self.triad_evaluator = TriadEvaluator(nim_client=self.nim_client)

    def _normalize_signal(self, value: float, lo: float, hi: float) -> float:
        """Normaliza un valor a señal en [-1, +1]."""
        if pd.isna(value):
            return 0.0
        return float(np.clip((value - lo) / (hi - lo) * 2 - 1, -1, 1))

    def _signal_from_binary(self, condition: bool, strength: float = 1.0) -> float:
        return strength if condition else -strength

    def _sentiment_regime_signal(self, df: pd.DataFrame,
                                 sentiment_data: Optional[Dict[str, float]]) -> Tuple[float, float, Optional[float]]:
        """Señal V1 (AAII bull-bear) como variable de régimen.

        Devuelve (s_v1, er20, spread):
        - s_v1: -normalize(spread) en [-1, +1]. Positivo = pesimismo (alcista,
          el sistema compra barato); negativo = euforia (bajista, el sistema
          distribuye). Sin datos de sentimiento -> 0.0 (neutro).
        - er20: Kaufman efficiency ratio del último día (default 0.5).
        - spread: valor crudo AAII o None si no hay datos.
        """
        s_v1, spread = 0.0, None
        if sentiment_data:
            spread = sentiment_data.get("aaii_bullbear_spread")
            if spread is not None and pd.notna(spread):
                s_v1 = -self._normalize_signal(float(spread), -AAII_SPREAD_BOUND, AAII_SPREAD_BOUND)
        if "er20" in df.columns and pd.notna(df["er20"].iloc[-1]):
            er = float(df["er20"].iloc[-1])
        else:
            er = 0.5
        return s_v1, er, spread


    # --------------------------------------------------------
    # 1. Señales técnicas (momentum y reversión)
    # --------------------------------------------------------

    def _technical_momentum_signals(self, df: pd.DataFrame) -> Tuple[List[SignalDetail], float]:
        """Señales de momentum basadas en los 15 indicadores técnicos."""
        signals: List[SignalDetail] = []
        latest = df.iloc[-1]

        # Momentum 12-1 (Jegadeesh & Titman 1993)
        if "momentum_12_1" in latest and pd.notna(latest["momentum_12_1"]):
            mom_signal = self._normalize_signal(latest["momentum_12_1"], -30, 60)
            signals.append(SignalDetail(
                name="Momentum 12-1",
                category="technical_momentum",
                value=float(latest["momentum_12_1"]),
                signal=mom_signal,
                weight=0.20,
                explanation="Momentum de 12 meses (Jegadeesh & Titman, 1993)"
            ))

        # Cruce SMAs (Brock et al. 1992)
        if "ema50" in latest and "ema200" in latest:
            sma_cross = 1.0 if latest["ema50"] > latest["ema200"] else -1.0
            if "close" in latest:
                price_above = 1.0 if latest["close"] > latest["ema200"] else -1.0
                signals.append(SignalDetail(
                    name="SMA 50/200 Golden Cross",
                    category="technical_momentum",
                    value=float(latest["ema50"] / latest["ema200"] - 1),
                    signal=sma_cross * 0.7 + price_above * 0.3,
                    weight=0.20,
                    explanation="Cruce de medias móviles 50/200 (Brock, Lakonishok & LeBaron, 1992)"
                ))

        # ADX (Wilder 1978)
        if "adx14" in latest and pd.notna(latest["adx14"]):
            adx = float(latest["adx14"])
            adx_signal = 0.0
            if adx > 40:
                adx_signal = 1.0
            elif adx > 25:
                adx_signal = 0.5
            elif adx > 20:
                adx_signal = 0.1
            signals.append(SignalDetail(
                name="ADX (fuerza de tendencia)",
                category="technical_momentum",
                value=adx,
                signal=adx_signal,
                weight=0.15,
                explanation="ADX > 25 indica tendencia fuerte (Wilder, 1978)"
            ))

        # MACD (Appel 1979, Chong & Ng 2008)
        if "macd" in latest and "macd_signal" in latest:
            macd = float(latest["macd"]) if pd.notna(latest["macd"]) else 0
            macd_sig = float(latest["macd_signal"]) if pd.notna(latest["macd_signal"]) else 0
            macd_hist = float(latest["macd_hist"]) if "macd_hist" in latest and pd.notna(latest["macd_hist"]) else 0
            cross = 1.0 if macd > macd_sig else -1.0
            hist_strength = np.tanh(macd_hist * 50) if pd.notna(macd_hist) else 0
            signals.append(SignalDetail(
                name="MACD",
                category="technical_momentum",
                value=macd_hist,
                signal=float(np.clip(cross * 0.6 + hist_strength * 0.4, -1, 1)),
                weight=0.15,
                explanation="Cruce MACD/signal (Appel 1979; Chong & Ng, 2008)"
            ))

        # Donchian Breakout (Sistema Turtle)
        if "donchian_breakout_buy" in latest and "donchian_breakout_sell" in latest:
            if latest["donchian_breakout_buy"]:
                donchian_signal = 1.0
            elif latest["donchian_breakout_sell"]:
                donchian_signal = -1.0
            else:
                donchian_signal = 0.0
            signals.append(SignalDetail(
                name="Donchian Breakout",
                category="technical_momentum",
                value=float(latest.get("donchian_upper", 0)),
                signal=donchian_signal,
                weight=0.10,
                explanation="Breakout de canal de 20 días (Sistema Turtle)"
            ))

        # Parabolic SAR
        if "sar_bullish" in latest:
            sar_signal = 1.0 if latest["sar_bullish"] else -1.0
            signals.append(SignalDetail(
                name="Parabolic SAR",
                category="technical_momentum",
                value=float(latest.get("parabolic_sar", 0)),
                signal=sar_signal,
                weight=0.10,
                explanation="SAR por debajo del precio = tendencia alcista (Wilder, 1978)"
            ))

        # Ichimoku Cloud
        if "ichimoku_cloud_bullish" in latest:
            ichimoku_signal = 1.0 if latest["ichimoku_cloud_bullish"] else -1.0
            signals.append(SignalDetail(
                name="Ichimoku Cloud",
                category="technical_momentum",
                value=1.0 if latest["ichimoku_cloud_bullish"] else 0.0,
                signal=ichimoku_signal,
                weight=0.10,
                explanation="Precio sobre la nube (Katsanos, 2008)"
            ))

        weighted_sum = sum(s.signal * s.weight for s in signals)
        total_weight = sum(s.weight for s in signals)
        score = weighted_sum / total_weight if total_weight > 0 else 0.0
        return signals, score

    def _technical_reversion_signals(self, df: pd.DataFrame) -> Tuple[List[SignalDetail], float]:
        """Señales de reversión a la media basadas en osciladores."""
        signals: List[SignalDetail] = []
        latest = df.iloc[-1]

        # RSI (Wilder 1978, Chong & Ng 2008)
        if "rsi14" in latest and pd.notna(latest["rsi14"]):
            rsi = float(latest["rsi14"])
            if rsi > 75:
                rsi_signal = -0.8  # Sobrecompra extrema
            elif rsi > 70:
                rsi_signal = -0.4
            elif rsi < 25:
                rsi_signal = 0.8   # Sobrevendido extremo
            elif rsi < 30:
                rsi_signal = 0.4
            elif 45 <= rsi <= 55:
                rsi_signal = 0.1
            else:
                rsi_signal = 0.0
            signals.append(SignalDetail(
                name="RSI 14",
                category="technical_reversion",
                value=rsi,
                signal=rsi_signal,
                weight=0.20,
                explanation="RSI > 70 sobrecompra, < 30 sobreventa (Wilder, 1978)"
            ))

        # Stochastic Oscillator (Lane 1984)
        if "stoch_k" in latest and pd.notna(latest["stoch_k"]):
            stoch = float(latest["stoch_k"])
            if stoch > 80:
                stoch_signal = -0.6
            elif stoch < 20:
                stoch_signal = 0.6
            else:
                stoch_signal = self._normalize_signal(stoch, 20, 80) * 0.5
            signals.append(SignalDetail(
                name="Estocástico %K",
                category="technical_reversion",
                value=stoch,
                signal=float(stoch_signal),
                weight=0.15,
                explanation="Oscilador estocástico con reversión de media (Lane, 1984)"
            ))

        # Williams %R
        if "williams_r" in latest and pd.notna(latest["williams_r"]):
            wr = float(latest["williams_r"])
            if wr < -80:
                wr_signal = 0.7
            elif wr > -20:
                wr_signal = -0.7
            else:
                wr_signal = self._normalize_signal(wr, -80, -20) * 0.5
            signals.append(SignalDetail(
                name="Williams %R",
                category="technical_reversion",
                value=wr,
                signal=float(wr_signal),
                weight=0.10,
                explanation="Williams %R sobrecompra/sobreventa (Williams, 1973)"
            ))

        # Bollinger Bands (Bollinger 1992, Lento et al. 2007)
        if "bb_upper" in latest and "bb_lower" in latest and "close" in latest:
            bb_upper = float(latest["bb_upper"])
            bb_lower = float(latest["bb_lower"])
            close = float(latest["close"])
            if close > bb_upper:
                bb_signal = -0.5
            elif close < bb_lower:
                bb_signal = 0.5
            else:
                # Posición dentro de las bandas
                bb_range = bb_upper - bb_lower
                position = (close - bb_lower) / bb_range if bb_range > 0 else 0.5
                bb_signal = self._normalize_signal(position, 0, 1) * 0.3
            signals.append(SignalDetail(
                name="Bandas de Bollinger",
                category="technical_reversion",
                value=position if 'position' in locals() else 0.5,
                signal=float(bb_signal),
                weight=0.15,
                explanation="Reversión a la media en extremos de bollinger (Lento et al., 2007)"
            ))

        # CCI (Lambert 1980)
        if "cci" in latest and pd.notna(latest["cci"]):
            cci_val = float(latest["cci"])
            cci_signal = float(np.clip(-cci_val / 200, -1, 1)) if abs(cci_val) > 100 else cci_val / 200
            signals.append(SignalDetail(
                name="CCI",
                category="technical_reversion",
                value=cci_val,
                signal=cci_signal,
                weight=0.10,
                explanation="Commodity Channel Index (Lambert, 1980)"
            ))

        # MFI (Money Flow Index)
        if "mfi14" in latest and pd.notna(latest["mfi14"]):
            mfi = float(latest["mfi14"])
            if mfi > 80:
                mfi_signal = -0.5
            elif mfi < 20:
                mfi_signal = 0.5
            else:
                mfi_signal = self._normalize_signal(mfi, 20, 80) * 0.4
            signals.append(SignalDetail(
                name="Money Flow Index",
                category="technical_reversion",
                value=mfi,
                signal=float(mfi_signal),
                weight=0.15,
                explanation="MFI combina precio y volumen (Eom et al., 2019)"
            ))

        weighted_sum = sum(s.signal * s.weight for s in signals)
        total_weight = sum(s.weight for s in signals)
        score = weighted_sum / total_weight if total_weight > 0 else 0.0
        return signals, score

    # --------------------------------------------------------
    # 2. Señales fundamentales
    # --------------------------------------------------------

    def _fundamental_signals(self, fundamentals: Optional[Dict]) -> Tuple[List[SignalDetail], float]:
        """
        Evalúa los 15 indicadores fundamentales.
        fundamentals debe incluir: pe_ratio, pb_ratio, ev_ebitda, roe, roa,
        debt_equity, fcf_yield, div_yield, eps_growth, gross_margin, peg,
        current_ratio, asset_turnover, book_value_growth, sue_score
        """
        signals: List[SignalDetail] = []
        if not fundamentals:
            return [], 0.0

        f = fundamentals

        # 1. P/E (Basu 1977)
        if f.get("pe_ratio"):
            pe = float(f["pe_ratio"])
            if pe > 0:
                pe_signal = self._normalize_signal(pe, 5, 60) * -1  # Inverso: bajo P/E = buena señal
            elif pe < 0:
                pe_signal = -0.8  # Ganancias negativas = mala señal
            else:
                pe_signal = 0.0
            signals.append(SignalDetail("P/E Ratio", "fundamental_value", pe, pe_signal, 0.12,
                                        "Bajo P/E predice mayores retornos (Basu, 1977)"))

        # 2. P/B (Fama & French 1992)
        if f.get("pb_ratio"):
            pb = float(f["pb_ratio"])
            if pb > 0:
                pb_signal = self._normalize_signal(pb, 0.5, 10) * -1
            else:
                pb_signal = 0.0
            signals.append(SignalDetail("P/B Ratio", "fundamental_value", pb, pb_signal, 0.12,
                                        "Book-to-market (Fama & French, 1992)"))

        # 3. EV/EBITDA (Loughran & Wellman 2011)
        if f.get("ev_ebitda"):
            ev = float(f["ev_ebitda"])
            if ev > 0:
                ev_signal = self._normalize_signal(ev, 3, 30) * -1
            else:
                ev_signal = 0.0
            signals.append(SignalDetail("EV/EBITDA", "fundamental_value", ev, ev_signal, 0.08,
                                        "EV/EBITDA controla estructura de capital (Loughran & Wellman, 2011)"))

        # 4. ROE (Fama & French 2006)
        if f.get("roe"):
            roe = float(f["roe"])
            roe_signal = self._normalize_signal(roe, -5, 30)
            signals.append(SignalDetail("ROE", "fundamental_growth", roe, roe_signal, 0.12,
                                        "Alta rentabilidad sobre equity (Fama & French, 2006)"))

        # 5. ROA (Sloan 1996)
        if f.get("roa"):
            roa = float(f["roa"])
            roa_signal = self._normalize_signal(roa, -3, 15)
            signals.append(SignalDetail("ROA", "fundamental_growth", roa, roa_signal, 0.08,
                                        "Calidad de ganancias (Sloan, 1996)"))

        # 6. Debt/Equity (Altman 1968)
        if f.get("debt_equity"):
            de = float(f["debt_equity"])
            de_signal = self._normalize_signal(de, 0, 3) * -1
            signals.append(SignalDetail("Debt/Equity", "fundamental_value", de, de_signal, 0.10,
                                        "Alto leverage aumenta riesgo de quiebra (Altman, 1968)"))

        # 7. Free Cash Flow Yield (Lakonishok et al. 1994)
        if f.get("fcf_yield"):
            fcf = float(f["fcf_yield"])
            fcf_signal = self._normalize_signal(fcf, -2, 10)
            signals.append(SignalDetail("FCF Yield", "fundamental_value", fcf, fcf_signal, 0.12,
                                        "FCF yield predice retornos (Lakonishok, Shleifer & Vishny, 1994)"))

        # 8. Dividend Yield (Fama & French 1988)
        if f.get("div_yield"):
            dy = float(f["div_yield"])
            dy_signal = self._normalize_signal(dy, 0, 6)
            signals.append(SignalDetail("Dividend Yield", "fundamental_value", dy, dy_signal, 0.06,
                                        "Div yield alto predice retornos (Fama & French, 1988)"))

        # 9. EPS Growth (Chan et al. 1996)
        if f.get("eps_growth"):
            eps = float(f["eps_growth"])
            eps_signal = self._normalize_signal(eps, -20, 50)
            signals.append(SignalDetail("EPS Growth", "fundamental_growth", eps, eps_signal, 0.15,
                                        "Momentum en ganancias (Chan, Jegadeesh & Lakonishok, 1996)"))

        # 10. Gross Margin (Novy-Marx 2013)
        if f.get("gross_margin"):
            gm = float(f["gross_margin"])
            gm_signal = self._normalize_signal(gm, 10, 60)
            signals.append(SignalDetail("Gross Margin", "fundamental_growth", gm, gm_signal, 0.12,
                                        "Gross profitability premium (Novy-Marx, 2013)"))

        # 11. PEG (Lynch 1989, Peters 1991)
        if f.get("peg"):
            peg = float(f["peg"])
            if peg > 0:
                peg_signal = self._normalize_signal(peg, 0, 3) * -1  # PEG < 1 bueno
            else:
                peg_signal = 0.0
            signals.append(SignalDetail("PEG Ratio", "fundamental_value", peg, peg_signal, 0.05,
                                        "PEG < 1 indica valor relativo a crecimiento (Peters, 1991)"))

        # 12. Current Ratio (Graham & Dodd 1934)
        if f.get("current_ratio"):
            cr = float(f["current_ratio"])
            cr_signal = self._normalize_signal(cr, 0.5, 3)
            signals.append(SignalDetail("Current Ratio", "fundamental_value", cr, cr_signal, 0.04,
                                        "Liquidez sana (Graham & Dodd, 1934)"))

        # 13. Asset Turnover (Fama & French 2006)
        if f.get("asset_turnover"):
            at = float(f["asset_turnover"])
            at_signal = self._normalize_signal(at, 0, 2)
            signals.append(SignalDetail("Asset Turnover", "fundamental_growth", at, at_signal, 0.04,
                                        "Eficiencia en uso de activos (Fama & French, 2006)"))

        # 14. Book Value Growth / Accruals (Sloan 1996)
        if f.get("book_value_growth"):
            bvg = float(f["book_value_growth"])
            bvg_signal = self._normalize_signal(bvg, -10, 30) * 0.7  # Reduce por calidad contable dudosa
            signals.append(SignalDetail("Book Value Growth", "fundamental_value", bvg, bvg_signal, 0.04,
                                        "Crecimiento contable (Sloan, 1996)"))

        # 15. SUE (Bernard & Thomas 1989)
        if f.get("sue_score"):
            sue = float(f["sue_score"])
            sue_signal = self._normalize_signal(sue, -3, 3)
            signals.append(SignalDetail("SUE (PEAD)", "fundamental_growth", sue, sue_signal, 0.15,
                                        "Post-Earnings Announcement Drift (Bernard & Thomas, 1989)"))

        if not signals:
            return [], 0.0

        # Separar value vs growth
        value_weight = sum(s.weight for s in signals if s.category == "fundamental_value")
        growth_weight = sum(s.weight for s in signals if s.category == "fundamental_growth")
        value_score = sum(s.signal * s.weight for s in signals if s.category == "fundamental_value") / value_weight if value_weight > 0 else 0
        growth_score = sum(s.signal * s.weight for s in signals if s.category == "fundamental_growth") / growth_weight if growth_weight > 0 else 0

        # Score combinado ponderado
        total_weight = value_weight + growth_weight
        score = (value_score * value_weight + growth_score * growth_weight) / total_weight if total_weight > 0 else 0
        return signals, float(score)

    # --------------------------------------------------------
    # 3. Señales macro (correlaciones entre activos)
    # --------------------------------------------------------

    def _macro_signals(self, macro_data: Optional[Dict[str, pd.DataFrame]]) -> Tuple[List[SignalDetail], float]:
        """
        Evalúa correlaciones macro. macro_data debe incluir:
        DXY, GC=F (gold), SI=F (silver), ^TNX (10Y yield), CL=F (oil), HG=F (copper)
        """
        signals: List[SignalDetail] = []
        if not macro_data:
            return [], 0.0

        dxy = macro_data.get("DXY")
        if dxy is None:
            dxy = macro_data.get("DX-Y.NYB")
        gold = macro_data.get("gold")
        if gold is None:
            gold = macro_data.get("GC=F")
        silver = macro_data.get("silver")
        if silver is None:
            silver = macro_data.get("SI=F")
        tlt = macro_data.get("TLT")
        sp500 = macro_data.get("SPY")
        if sp500 is None:
            sp500 = macro_data.get("^GSPC")
        oil = macro_data.get("oil")
        if oil is None:
            oil = macro_data.get("CL=F")
        copper = macro_data.get("copper")
        if copper is None:
            copper = macro_data.get("HG=F")

        # Regla 1: DXY bajando + Oro subiendo → Risk-ON
        # IC medido: +0.057, dirección correcta. Peso reponderado
        # proporcional a |IC| junto con Petróleo y SPY (las 3 reglas con
        # evidencia real).
        if dxy is not None and gold is not None and len(dxy) > 30 and len(gold) > 30:
            dxy_ret_20d = float(dxy["close"].pct_change(20).iloc[-1] * 100)
            gold_ret_20d = float(gold["close"].pct_change(20).iloc[-1] * 100)

            if dxy_ret_20d < -1 and gold_ret_20d > 1:
                risk_on = 0.8
                explain = "DXY baja + Oro sube = Risk-ON (alcista para acciones)"
            elif dxy_ret_20d > 1 and gold_ret_20d < -1:
                risk_on = -0.8
                explain = "DXY sube + Oro baja = Risk-OFF (bajista para acciones)"
            else:
                risk_on = self._normalize_signal(-dxy_ret_20d + gold_ret_20d, -5, 5) * 0.5
                explain = "Señal combinada DXY/Oro"
            signals.append(SignalDetail("DXY vs Oro (Risk Switch)", "macro", dxy_ret_20d,
                                        float(risk_on), 0.2588, explain))

        # Regla 2: Gold/Silver ratio
        # IC medido (diagnose_macro_ic.py, pooled 2019-2024, n=2086): -0.024,
        # débil. Se mantiene como contexto informativo (útil para que un
        # humano entienda la recomendación) pero con weight=0 para que no
        # mueva el score compuesto — no hay evidencia suficiente para
        # confiar en la dirección de esta regla.
        if gold is not None and silver is not None:
            gs_ratio = compute_gold_silver_ratio(gold["close"], silver["close"]).iloc[-1]
            if gs_ratio > 80:
                gs_signal = -0.6  # Miedo
                explain = "Gold/Silver > 80 = señal de miedo"
            elif gs_ratio < 65:
                gs_signal = 0.6   # Optimismo
                explain = "Gold/Silver < 65 = señal de optimismo"
            else:
                gs_norm = self._normalize_signal(gs_ratio, 65, 80) * -0.4
                gs_signal = float(gs_norm)
                explain = "Gold/Silver ratio en rango neutral"
            signals.append(SignalDetail("Gold/Silver Ratio", "macro", float(gs_ratio),
                                        gs_signal, 0.0, explain))

        # Regla 3: Cobre como leading indicator
        # IC medido: +0.015, prácticamente nulo. Igual tratamiento: se
        # informa pero no pesa en el score.
        if copper is not None and len(copper) > 200:
            copper_above_200 = float(copper["close"].iloc[-1] > copper["close"].rolling(200).mean().iloc[-1])
            copper_signal = 0.8 if copper_above_200 else -0.8
            signals.append(SignalDetail("Cobre vs MA200 (Expansión)", "macro", copper_above_200,
                                        copper_signal, 0.0,
                                        "Cobre sobre MA200 = expansión económica (alcista)"))

        # Regla 4: Bonds 10Y con Oro (estanflación)
        # IC medido: +0.0097, esencialmente cero. Mismo tratamiento.
        if tlt is not None and gold is not None:
            tlt_recent = float(tlt["close"].pct_change(20).iloc[-1] * 100)
            gold_recent = float(gold["close"].pct_change(20).iloc[-1] * 100)
            # TLT bajando = yields subiendo
            if tlt_recent < -1 and gold_recent > 1:
                stagflation = -0.7
                explain = "Yields suben + Oro sube = posible estanflación (bajista)"
            elif tlt_recent > 1 and gold_recent > 1:
                stagflation = 0.7
                explain = "Yields bajan + Oro sube = liquidez (alcista)"
            else:
                stagflation = 0.0
                explain = "Señal de bonos neutral"
            signals.append(SignalDetail("Bonos 10Y + Oro (Inflación)", "macro", tlt_recent,
                                        stagflation, 0.0, explain))

        # Regla 5: SPY momentum como mercado general
        # IC medido: -0.10 — la señal macro más fuerte de las 6, pero
        # INVERTIDA: momentum fuerte del SPY predijo peor retorno futuro a
        # 20 días para las acciones individuales (reversión a nivel índice
        # en ese horizonte), no mejor. Se invierte el signo en vez de
        # descartarla, porque la magnitud (4x más grande que Gold/Silver) y
        # el tamaño de muestra (n=2086) dan confianza suficiente para
        # confiar en la dirección opuesta, a diferencia de las reglas
        # débiles de arriba.
        if sp500 is not None and len(sp500) > 50:
            spy_ret = float(sp500["close"].pct_change(50).iloc[-1] * 100)
            spy_signal = -self._normalize_signal(spy_ret, -10, 15)
            signals.append(SignalDetail("S&P 500 Momentum 50d (invertido, IC medido)", "macro", spy_ret,
                                        spy_signal, 0.4543,
                                        "Momentum fuerte del mercado predijo peor retorno futuro (reversión)"))

        # Regla 6: Petróleo
        # IC medido: +0.063, dirección correcta.
        if oil is not None and len(oil) > 20:
            oil_ret = float(oil["close"].pct_change(20).iloc[-1] * 100)
            # Petróleo baja = presión inflacionaria baja = alcista; sube mucho = inflación = bajista
            if oil_ret > 10:
                oil_signal = -0.4
            elif oil_ret < -10:
                oil_signal = 0.4
            else:
                oil_signal = 0.0
            signals.append(SignalDetail("Petróleo (Inflación)", "macro", oil_ret,
                                        oil_signal, 0.2869, "Movimiento extremo de petróleo"))

        if not signals:
            return [], 0.0

        score = sum(s.signal * s.weight for s in signals) / sum(s.weight for s in signals)
        return signals, float(score)

    # --------------------------------------------------------
    # 4. Detección de manipulación institucional
    # --------------------------------------------------------

    def _manipulation_signals(self, df: pd.DataFrame) -> Tuple[List[SignalDetail], float, List[str]]:
        """Detecta patrones de manipulación institucional."""
        signals: List[SignalDetail] = []
        manipulation_warnings: List[str] = []
        latest = df.iloc[-1]

        # Señal 1: Divergencia RSI/precio (distribución)
        if "bearish_divergence" in latest and latest["bearish_divergence"]:
            signals.append(SignalDetail(
                "Divergencia RSI (Distribución)", "sentiment_manipulation", 1.0, -0.8, 0.20,
                "Precio sube pero RSI baja = posible distribución institucional"
            ))
            manipulation_warnings.append("Divergencia bajista: precio sube, RSI baja")

        if "bullish_divergence" in latest and latest["bullish_divergence"]:
            signals.append(SignalDetail(
                "Divergencia RSI (Acumulación)", "sentiment_manipulation", 1.0, 0.7, 0.20,
                "Precio baja pero RSI sube = posible acumulación institucional"
            ))
            manipulation_warnings.append("Divergencia alcista: precio baja, RSI sube")

        # Señal 2: Divergencia volumen/precio (distribución o rally falso)
        if "volume_divergence" in latest:
            vol_div = float(latest["volume_divergence"])
            if vol_div > 0.5:
                signals.append(SignalDetail(
                    "Rally sin volumen (Falsa convicción)", "sentiment_manipulation", vol_div, -0.6, 0.15,
                    "Precio sube con volumen decreciente = rally no confirmado"
                ))
                manipulation_warnings.append("Precio sube con volumen decreciente")
            elif vol_div < -0.5:
                signals.append(SignalDetail(
                    "Capitulación con volumen", "sentiment_manipulation", vol_div, 0.6, 0.15,
                    "Precio baja con volumen alto = posible fondo o venta masiva"
                ))
                manipulation_warnings.append("Volumen alto en caída = posible capitulación")

        # Señal 3: CMF (Chaikin Money Flow)
        if "cmf20" in latest and pd.notna(latest["cmf20"]):
            cmf = float(latest["cmf20"])
            if cmf > 0.2:
                cmf_signal = 0.8
                explain = "CMF > 0.2 = acumulación fuerte"
            elif cmf < -0.2:
                cmf_signal = -0.8
                explain = "CMF < -0.2 = distribución fuerte"
                manipulation_warnings.append("CMF negativo fuerte: distribución institucional")
            else:
                cmf_signal = float(np.clip(cmf * 4, -0.5, 0.5))
                explain = "CMF neutral"
            signals.append(SignalDetail("Chaikin Money Flow", "sentiment_manipulation", cmf,
                                        cmf_signal, 0.20, explain))

        # Señal 4: A/D Line trend
        if "ad_trend_bullish" in latest and "ad_line" in latest:
            ad_signal = 0.5 if latest["ad_trend_bullish"] else -0.5
            signals.append(SignalDetail(
                "A/D Line (Acumulación)", "sentiment_manipulation",
                float(latest["ad_line"]) if pd.notna(latest.get("ad_line")) else 0.0,
                ad_signal, 0.15,
                "Accumulation/Distribution Line en tendencia alcista o bajista"
            ))
            if not latest["ad_trend_bullish"] and "ad_line" in latest:
                manipulation_warnings.append("La línea de acumulación/distribución está cayendo")

        # Señal 5: Smart Money Index proxy
        if "smi_proxy" in latest and pd.notna(latest["smi_proxy"]):
            smi = float(latest["smi_proxy"])
            smi_signal = float(np.clip(smi * 5, -1, 1))  # smi_proxy ~ [-0.2, 0.2]
            signals.append(SignalDetail(
                "Smart Money Proxy", "sentiment_manipulation", smi, smi_signal, 0.15,
                "Proxi de presión institucional al cierre"
            ))

        # Señal 6: OBV trend
        if "obv_trend_bullish" in latest:
            obv_signal = 0.4 if latest["obv_trend_bullish"] else -0.4
            signals.append(SignalDetail(
                "On-Balance Volume", "sentiment_manipulation",
                1.0 if latest["obv_trend_bullish"] else 0.0,
                obv_signal, 0.15,
                "OBV sobre su media = flujo neto positivo"
            ))

        if not signals:
            return [], 0.0, manipulation_warnings

        score = sum(s.signal * s.weight for s in signals) / sum(s.weight for s in signals)
        return signals, float(score), manipulation_warnings

    # --------------------------------------------------------
    # 5. Volatilidad y liquidez
    # --------------------------------------------------------

    def _volatility_liquidity_signals(self, df: pd.DataFrame, vix_data: Optional[pd.DataFrame] = None) -> Tuple[List[SignalDetail], float]:
        """Evalúa volatilidad y liquidez."""
        signals: List[SignalDetail] = []
        latest = df.iloc[-1]

        # Volatilidad realizada
        returns = df["close"].pct_change().dropna().tail(20)
        realized_vol = float(returns.std() * np.sqrt(252) * 100) if len(returns) > 5 else 30.0

        if realized_vol > 40:
            vol_signal = -0.5  # Volatilidad alta = riesgo
        elif realized_vol < 15:
            vol_signal = 0.3   # Baja volatilidad premium
        else:
            vol_signal = self._normalize_signal(realized_vol, 15, 40) * -1
        signals.append(SignalDetail("Volatilidad Realizada", "volatility_liquidity",
                                    realized_vol, float(vol_signal), 0.30,
                                    "Volatilidad alta reduce retornos ajustados por riesgo"))

        # VIX si está disponible (Whaley 2000)
        if vix_data is not None and len(vix_data) > 20:
            vix = float(vix_data["close"].iloc[-1])
            if vix > 30:
                vix_signal = -0.8
            elif vix > 25:
                vix_signal = -0.4
            elif vix < 15:
                vix_signal = 0.3
            else:
                vix_signal = 0.0
            signals.append(SignalDetail("VIX (Gauge de miedo)", "volatility_liquidity",
                                        vix, float(vix_signal), 0.30,
                                        "VIX > 30 = miedo extremo (Whaley, 2000)"))

        # Liquidez: volumen ratio (Amihud 2002)
        if "volume_ratio" in latest and pd.notna(latest.get("volume_ratio")):
            vr = float(latest["volume_ratio"])
            if vr > 2.5:
                liq_signal = -0.3  # Volumen inusualmente alto = posible evento
            elif vr < 0.5:
                liq_signal = -0.2  # Muy poca actividad = iliquidez
            else:
                liq_signal = 0.4   # Volumen saludable
            signals.append(SignalDetail("Liquidez (Volumen)", "volatility_liquidity",
                                        vr, liq_signal, 0.20,
                                        "Ratio de volumen saludable o extremo (Amihud, 2002)"))

        # ATR como medida de riesgo
        if "atr14" in latest and pd.notna(latest["atr14"]) and "close" in latest:
            atr_pct = float(latest["atr14"] / latest["close"] * 100)
            if atr_pct > 5:
                atr_signal = -0.4
            elif atr_pct < 1:
                atr_signal = 0.3
            else:
                atr_signal = self._normalize_signal(atr_pct, 1, 5) * -1
            signals.append(SignalDetail("ATR % (Riesgo)", "volatility_liquidity",
                                        atr_pct, float(atr_signal), 0.20,
                                        "ATR relativo al precio"))

        if not signals:
            return [], 0.0

        score = sum(s.signal * s.weight for s in signals) / sum(s.weight for s in signals)
        return signals, float(score)

    # --------------------------------------------------------
    # 6. Señales de Polymarket-like (probabilidades macro)
    # --------------------------------------------------------

    def _prediction_market_signals(self, prediction_data: Optional[Dict[str, float]]) -> Tuple[List[SignalDetail], float]:
        """
        Integra señales de mercados de predicción.
        prediction_data debe incluir: recession_prob, fed_cut_prob,
        inflation_prob, default_prob, unemployment_prob
        Fuente: Wolfers & Zitzewitz (2004)
        """
        signals: List[SignalDetail] = []
        if not prediction_data:
            return [], 0.0

        p = prediction_data

        # Probabilidad de recesión
        if p.get("recession_prob") is not None:
            rec = float(p["recession_prob"])
            rec_signal = -rec  # Mayor probabilidad de recesión = más negativo
            signals.append(SignalDetail("Polymarket: Recesión", "sentiment_manipulation",
                                        rec, float(rec_signal), 0.25,
                                        "Probabilidad de recesión → P/E compression"))

        # Recorte de tasas Fed
        if p.get("fed_cut_prob") is not None:
            cut = float(p["fed_cut_prob"])
            cut_signal = cut * 0.8 - 0.3  # > 50% recorte = positivo
            signals.append(SignalDetail("Polymarket: Recorte Fed", "sentiment_manipulation",
                                        cut, float(cut_signal), 0.20,
                                        "Recorte de tasas = liquidez = alcista"))

        # Inflación elevada
        if p.get("inflation_prob") is not None:
            inf = float(p["inflation_prob"])
            inf_signal = -inf * 0.7
            signals.append(SignalDetail("Polymarket: Inflación > 4%", "sentiment_manipulation",
                                        inf, float(inf_signal), 0.20,
                                        "Inflación alta erosiona múltiplos"))

        # Probabilidad de default
        if p.get("default_prob") is not None:
            default = float(p["default_prob"])
            default_signal = -default
            signals.append(SignalDetail("Polymarket: Default EEUU", "sentiment_manipulation",
                                        default, float(default_signal), 0.15,
                                        "Riesgo sistémico"))

        # Desempleo
        if p.get("unemployment_prob") is not None:
            unemp = float(p["unemployment_prob"])
            unemp_signal = -unemp * 0.6
            signals.append(SignalDetail("Polymarket: Desempleo", "sentiment_manipulation",
                                        unemp, float(unemp_signal), 0.10,
                                        "Desempleo alto impacta consumo"))

        if not signals:
            return [], 0.0

        score = sum(s.signal * s.weight for s in signals) / sum(s.weight for s in signals)
        return signals, float(score)

    # --------------------------------------------------------
    # 7. Probabilidad calibrada (Platt scaling)
    # --------------------------------------------------------

    def _probability_from_score(self, score: float, horizon: str) -> float:
        """Convierte score compuesto a probabilidad usando logística calibrada."""
        # Calibración por horizonte (k más alto = mayor sensibilidad)
        k_map = {
            "short_term_1_30d": 1.8,
            "medium_term_1_6m": 1.5,
            "long_term_1_5y": 1.2,
        }
        k = k_map.get(horizon, 1.5)
        prob = 1 / (1 + np.exp(-k * score))
        return float(np.clip(prob, 0.05, 0.95))

    # --------------------------------------------------------
    # 8. Método público principal
    # --------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        regime_state: int = 0,
        fundamentals: Optional[Dict] = None,
        macro_data: Optional[Dict[str, pd.DataFrame]] = None,
        prediction_data: Optional[Dict[str, float]] = None,
        vix_data: Optional[pd.DataFrame] = None,
        sentiment_data: Optional[Dict[str, float]] = None,
    ) -> PredictionResult:
        """
        Analiza un símbolo y genera recomendación probabilística.

        Args:
            symbol: Símbolo (e.g., "AAPL")
            df: DataFrame con OHLCV + indicadores base
            regime_state: Estado de régimen (0-3) del GlobalRegimeClassifier
            fundamentals: Dict con 15 ratios fundamentales
            macro_data: Dict con DataFrames de DXY, gold, silver, etc.
            prediction_data: Dict con probabilidades de Polymarket-like
            vix_data: DataFrame con datos de VIX
            sentiment_data: Dict con el valor de sentimiento alineado
                (e.g., {"aaii_bullbear_spread": -23.4}). V1 entra al
                compuesto con peso 0.50 (PLAN_SENTIMIENTO.md §7).
        """
        # Calcular indicadores predictivos
        df = df.copy()
        if "adx14" not in df.columns:
            # Merge with base indicators
            from app.core.indicators import calculate_all_indicators
            df_with_indicators = calculate_all_indicators(df)
            # Preserve existing columns if present
            for col in df_with_indicators.columns:
                if col not in df.columns:
                    df[col] = df_with_indicators[col]
        df = calculate_predictive_indicators(df)
        df = df.dropna(subset=["close"])

        # Scores por categoría
        tech_mom_signals, tech_mom_score = self._technical_momentum_signals(df)
        tech_rev_signals, tech_rev_score = self._technical_reversion_signals(df)
        fund_signals, fund_score = self._fundamental_signals(fundamentals)
        macro_signals, macro_score = self._macro_signals(macro_data)
        manip_signals, manip_score, manipulation_warnings = self._manipulation_signals(df)
        vol_signals, vol_score = self._volatility_liquidity_signals(df, vix_data)
        pred_market_signals, pred_market_score = self._prediction_market_signals(prediction_data)

        # Combinar señales de sentimiento (manipulación + prediction markets)
        all_sentiment_signals = manip_signals + pred_market_signals
        if all_sentiment_signals:
            sentiment_score = sum(s.signal * s.weight for s in all_sentiment_signals) / sum(s.weight for s in all_sentiment_signals)
        else:
            sentiment_score = 0.0

        # Inicializar growth_score
        growth_score = 0.0

        # Capa de régimen de sentimiento V1 (pre-registrada §7: peso 0.50)
        s_v1, er20, aaii_spread = self._sentiment_regime_signal(df, sentiment_data)
        sentiment_regime_signals: List[SignalDetail] = []

        # H6: en euforia extrema, momentum/RSI/ER pierden poder e invierten
        # (IC condicional RSI -0.1254, ER -0.1122 @60d en el bucket alto) ->
        # el régimen los cuestiona reduciendo su aporte antes del compuesto.
        if aaii_spread is not None and s_v1 < -SENTIMENT_EXTREME:
            tech_mom_score *= 0.5
            tech_rev_score *= 0.5
            sentiment_regime_signals.append(SignalDetail(
                name="Cuestionamiento euforia (H6)",
                category="sentiment_regime",
                value=float(aaii_spread),
                signal=-1.0,
                weight=0.5,
                explanation="Euforia AAII extrema: momentum/RSI/ER se cuestionan (IC condicional invierte)"
            ))

        # Pesos según régimen
        weights = REGIME_WEIGHTS.get(regime_state, REGIME_WEIGHTS[0])

        # Score compuesto
        composite = 0.0
        composite += tech_mom_score * weights["technical_momentum"]
        composite += tech_rev_score * weights["technical_reversion"]
        composite += fund_score * weights["fundamental_value"]
        composite += macro_score * weights["macro"]
        composite += sentiment_score * weights["sentiment_manipulation"]
        composite += vol_score * weights["volatility_liquidity"]

        # Ajustar por crecimiento fundamental si disponible
        if fund_signals:
            growth_weight = sum(s.weight for s in fund_signals if s.category == "fundamental_growth")
            growth_score = sum(s.signal * s.weight for s in fund_signals if s.category == "fundamental_growth") / growth_weight if growth_weight > 0 else 0
            composite += growth_score * weights.get("fundamental_growth", 0.10)

        # V1 entra al compuesto con peso dominante 0.50 (blend pre-registrado §7)
        if aaii_spread is not None:
            composite = (1.0 - SENTIMENT_REGIME_DOMINANCE) * composite + SENTIMENT_REGIME_DOMINANCE * s_v1
            sentiment_regime_signals.append(SignalDetail(
                name="Sentiment Regime V1 (AAII)",
                category="sentiment_regime",
                value=float(aaii_spread),
                signal=s_v1,
                weight=SENTIMENT_REGIME_DOMINANCE,
                explanation="AAII bull-bear con peso dominante 0.50 (PLAN_SENTIMIENTO.md §7)"
            ))

            # V4: velocidad de la subida + sentimiento
            if er20 < ER_SLOW and s_v1 > 0.3:
                composite += 0.10
                sentiment_regime_signals.append(SignalDetail(
                    name="Acumulación silenciosa (V4)",
                    category="sentiment_regime",
                    value=float(aaii_spread),
                    signal=1.0,
                    weight=0.10,
                    explanation=f"Subida lenta (ER20={er20:.2f}) con pesimismo: acumulación, se confirma continuidad"
                ))
            elif er20 > ER_FAST and s_v1 < -0.3:
                composite -= 0.10
                sentiment_regime_signals.append(SignalDetail(
                    name="Distribución en euforia (V4)",
                    category="sentiment_regime",
                    value=float(aaii_spread),
                    signal=-1.0,
                    weight=0.10,
                    explanation=f"Subida rápida (ER20={er20:.2f}) con euforia: distribución, inclinación bajista"
                ))

        # Determinar decisión
        decision = "MANTENER"
        confidence = "Baja"
        for label, threshold in DECISION_THRESHOLDS:
            if composite > threshold:
                decision = label
                break
        if abs(composite) > 0.55:
            confidence = "Alta"
        elif abs(composite) > 0.30:
            confidence = "Media"

        # Nombre del régimen
        regime_names = {0: "Crecimiento normal", 1: "Riesgo elevado", 2: "Rango lateral", 3: "Turbulento"}
        regime_name = regime_names.get(regime_state, "Desconocido")

        # Probabilidades por horizonte
        # El término extra `composite * weights.get("technical_reversion", 0)`
        # que había acá antes rompía el patrón de los otros dos horizontes
        # (los 4 pesos ya suman 1.0) y contaba tech_rev_score dos veces
        # (directo + diluido dentro de composite). Auditado y sacado.
        prob_up_short = self._probability_from_score(tech_rev_score * 0.4 + vol_score * 0.25 +
                                                     sentiment_score * 0.20 + tech_mom_score * 0.15,
                                                     "short_term_1_30d")
        prob_up_medium = self._probability_from_score(tech_mom_score * 0.30 + tech_rev_score * 0.15 +
                                                      macro_score * 0.20 + growth_score * 0.15 +
                                                      sentiment_score * 0.10 + vol_score * 0.10,
                                                      "medium_term_1_6m")
        prob_up_long = self._probability_from_score(fund_score * 0.45 + macro_score * 0.25 +
                                                    tech_mom_score * 0.15 + sentiment_score * 0.05 +
                                                    tech_rev_score * 0.05 + growth_score * 0.05,
                                                    "long_term_1_5y")

        # Todos los detalles de señales
        all_signals = tech_mom_signals + tech_rev_signals + fund_signals + macro_signals + \
                      manip_signals + vol_signals + pred_market_signals + sentiment_regime_signals

        # Evaluación TRIAD (triple validación independiente)
        triad = self.triad_evaluator.evaluate(df, symbol=symbol, fundamentals=fundamentals,
                                              macro_data=macro_data, sentiment_data=sentiment_data)

        # Ajustar score compuesto con consenso TRIAD (20% peso)
        composite_with_triad = composite * 0.8 + triad.consensus_score * 0.2

        # Recalcular decisión con TRIAD
        decision = "MANTENER"
        confidence = "Baja"
        for label, threshold in DECISION_THRESHOLDS:
            if composite_with_triad > threshold:
                decision = label
                break
        if abs(composite_with_triad) > 0.55:
            confidence = "Alta"
        elif abs(composite_with_triad) > 0.30:
            confidence = "Media"

        result = PredictionResult(
            symbol=symbol,
            timestamp=str(pd.Timestamp.now()),
            regime_state=regime_state,
            regime_name=regime_name,
            technical_score=float((tech_mom_score * weights["technical_momentum"] +
                                   tech_rev_score * weights["technical_reversion"]) /
                                  (weights["technical_momentum"] + weights["technical_reversion"]) if (weights["technical_momentum"] + weights["technical_reversion"]) > 0 else 0),
            fundamental_score=float(fund_score),
            macro_score=float(macro_score),
            sentiment_score=float(sentiment_score),
            volatility_score=float(vol_score),
            composite_score=float(composite_with_triad),
            decision=decision,
            confidence=confidence,
            prob_up_short=float(prob_up_short),
            prob_up_medium=float(prob_up_medium),
            prob_up_long=float(prob_up_long),
            signals=all_signals,
            manipulation_risk=float(abs(min(manip_score, 0))),
            manipulation_signals=manipulation_warnings,
            triad_consensus=triad,
            triad_score=float(triad.consensus_score),
            triad_recommendation=triad.final_recommendation,
            triad_agreement=triad.agreement_level,
        )
        return result

    # --------------------------------------------------------
    # 9. Análisis de correlaciones macro en vivo
    # --------------------------------------------------------

    def analyze_macro_correlations(self, macro_data: Dict[str, pd.DataFrame]) -> Dict:
        """Analiza correlaciones actuales entre activos macro."""
        correlations = {}
        assets = list(macro_data.keys())
        for i, a in enumerate(assets):
            for b in assets[i+1:]:
                if a in macro_data and b in macro_data:
                    da = macro_data[a]
                    db = macro_data[b]
                    if len(da) > 30 and len(db) > 30:
                        corr = da["close"].tail(60).corr(db["close"].tail(60))
                        correlations[f"{a}_{b}"] = {
                            "correlation": round(float(corr), 3),
                            "historical_avg": MACRO_CORRELATIONS.get(a, {}).get(b,
                                                MACRO_CORRELATIONS.get(b, {}).get(a, 0)),
                            "deviation": round(float(corr - MACRO_CORRELATIONS.get(a, {}).get(b,
                                                  MACRO_CORRELATIONS.get(b, {}).get(a, 0))), 3),
                        }
        return correlations


def format_recommendation(result: PredictionResult) -> str:
    """Formatea el resultado para display humano."""
    lines = [
        f"=== {result.symbol} — {result.decision} ===",
        f"Régimen: {result.regime_name} | Confianza: {result.confidence}",
        f"Score compuesto: {result.composite_score:.3f}",
        "",
        "Probabilidades de subida:",
        f"  Corto plazo (1-30d):  {result.prob_up_short:.1%}",
        f"  Mediano plazo (1-6m): {result.prob_up_medium:.1%}",
        f"  Largo plazo (1-5y):   {result.prob_up_long:.1%}",
        "",
        "Scores por categoría:",
        f"  Técnico:     {result.technical_score:+.3f}",
        f"  Fundamental: {result.fundamental_score:+.3f}",
        f"  Macro:       {result.macro_score:+.3f}",
        f"  Sentimiento: {result.sentiment_score:+.3f}",
        f"  Volatilidad: {result.volatility_score:+.3f}",
        "",
        "TRIAD Consensus:",
        f"  🐂 BULL:       {result.triad_consensus.bull_score:+.3f}" if result.triad_consensus else "  TRIAD no disponible",
        f"  🐻 BEAR:       {result.triad_consensus.bear_score:+.3f}" if result.triad_consensus else "",
        f"  🔄 CONTRARIAN: {result.triad_consensus.contrarian_score:+.3f}" if result.triad_consensus else "",
        f"  Consenso: {result.triad_score:+.3f} | Acuerdo: {result.triad_agreement} | Rec: {result.triad_recommendation}",
    ]
    if result.manipulation_signals:
        lines.append("")
        lines.append("⚠️ Señales de manipulación detectadas:")
        for w in result.manipulation_signals:
            lines.append(f"  • {w}")
    return "\n".join(lines)
