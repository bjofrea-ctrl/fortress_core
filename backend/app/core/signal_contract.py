"""
Contrato de señal única — B6 (PLAN_REMEDIO_BRECHAS_20260903).

ÚNICA fuente de verdad para la definición congelada de la señal mensual.
Los 3 consumidores (signal_engine, validacion_oos, pipeline_daily_signal)
importan DESDE ACÁ — jamás redefinen lógica de scoring/gates.

Condición innegociable: golden tests que prueban señal bit-idéntica
pre/post refactor sobre el universo completo, 60 días corridos.
Si un solo valor difiere → rollback. Solo con golden 100% se despliega.
"""
from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np
import pandas as pd


# ─── Constantes congeladas (eco de validacion_oos_fresca_mom_rsi.py) ───
ENTRY_THRESHOLD = 0.60
RSI_SCORE_BAND = (45, 70)   # banda de scoring (no gate)
RSI_GATE = (40, 75)         # gate duro de entrada
ADX_MIN = 20
VR_MIN = 1.0

# Pesos base (priors) derivados de diagnose_factor_ic pooled 2019-2024
# momentum IC=0.0637, rsi IC=0.0322 -> peso proporcional a |IC|
_MOMENTUM_IC = 0.0637
_RSI_IC = 0.0322
_MOM_W = _MOMENTUM_IC / (_MOMENTUM_IC + _RSI_IC)
_RSI_W = 1.0 - _MOM_W

FACTOR_WEIGHTS_BASE = {
    regime: {"momentum": round(_MOM_W, 4), "rsi": round(_RSI_W, 4)}
    for regime in (0, 1, 2, 3)
}


@dataclass(frozen=True)
class SignalContract:
    """Contrato inmutable de la señal congelada."""
    entry_threshold: float = ENTRY_THRESHOLD
    rsi_score_band: tuple = RSI_SCORE_BAND
    rsi_gate: tuple = RSI_GATE
    adx_min: int = ADX_MIN
    vr_min: float = VR_MIN
    factor_weights: Dict[int, Dict[str, float]] = None  # type: ignore

    def __post_init__(self):
        if self.factor_weights is None:
            object.__setattr__(self, "factor_weights", FACTOR_WEIGHTS_BASE)


# Instancia singleton del contrato
CONTRACT = SignalContract()


def normalize(value: float, lo: float, hi: float) -> float:
    """Normalización [lo, hi] -> [0, 1] con clip."""
    return float(np.clip((value - lo) / (hi - lo), 0, 1))


def momentum_score(momentum_12_1: float) -> float:
    """Score de momentum: normalizado [-50, 100] -> [0, 1], NaN -> 0.5."""
    if not np.isfinite(momentum_12_1):
        return 0.5
    return normalize(momentum_12_1, -50.0, 100.0)


def rsi_score(rsi14: float) -> float:
    """Score de RSI: 0.8 si 45<rsi<70, 0.4 en caso contrario, NaN -> 0.5."""
    if not np.isfinite(rsi14):
        return 0.5
    lo, hi = RSI_SCORE_BAND
    return 0.8 if lo < rsi14 < hi else 0.4


def factor_scores(latest_row: pd.Series) -> Dict[str, float]:
    """
    Scores de factores para la última fila (una sola barra).
    Usado por generate_signal() y latest_signal().
    """
    return {
        "momentum": momentum_score(latest_row.get("momentum_12_1", np.nan)),
        "rsi": rsi_score(latest_row.get("rsi14", np.nan)),
    }


def compute_score_series(indicators_df: pd.DataFrame, regime_state: int = 0) -> pd.Series:
    """
    Score compuesto vectorizado para toda la serie (no solo última barra).
    Usado por diagnóstico walk-forward y pipeline_daily_signal.
    """
    mom = indicators_df.get("momentum_12_1", pd.Series(np.nan, index=indicators_df.index))
    momentum_vec = ((mom + 50) / 150).clip(0, 1)
    momentum_vec = momentum_vec.where(mom.notna(), 0.5)

    rsi = indicators_df.get("rsi14", pd.Series(np.nan, index=indicators_df.index))
    rsi_vec = pd.Series(
        np.where(rsi.between(45, 70, inclusive="neither"), 0.8, 0.4),
        index=indicators_df.index,
    ).where(rsi.notna(), 0.5)

    weights = CONTRACT.factor_weights.get(regime_state, CONTRACT.factor_weights[0])
    return momentum_vec * weights["momentum"] + rsi_vec * weights["rsi"]


def compute_factor_frame(indicators_df: pd.DataFrame) -> pd.DataFrame:
    """
    Componentes de factor individuales + máscara de elegibilidad
    reproduciendo los filtros duros de la definición congelada.
    """
    df = indicators_df
    mom = df.get("momentum_12_1", pd.Series(np.nan, index=df.index))
    momentum = ((mom + 50) / 150).clip(0, 1)

    trend_ok = (df["close"] > df["ema50"]) & (df["ema50"] > df["ema200"])
    trend = pd.Series(np.where(trend_ok, 1.0, 0.0), index=df.index)

    rsi = df.get("rsi14", pd.Series(np.nan, index=df.index))
    rsi_s = pd.Series(np.where(rsi.between(45, 70, inclusive="neither"), 0.8, 0.4), index=df.index)
    rsi_s = rsi_s.where(rsi.notna())

    adx = df.get("adx14", pd.Series(np.nan, index=df.index))
    adx_s = pd.Series(np.where(adx > 25, 0.9, 0.3), index=df.index)
    adx_s = adx_s.where(adx.notna())

    vol_ratio = df.get("volume_ratio", pd.Series(np.nan, index=df.index))
    eligible = trend_ok & (adx >= ADX_MIN) & (rsi > RSI_GATE[0]) & (rsi < RSI_GATE[1]) & (vol_ratio >= VR_MIN)

    return pd.DataFrame({
        "momentum": momentum, "trend": trend, "rsi": rsi_s, "adx": adx_s,
        "eligible": eligible.fillna(False), "close": df["close"],
    }, index=df.index)


def is_eligible(latest_row: pd.Series) -> bool:
    """
    Evalúa gates duros de entrada sobre una fila individual.
    Réplica exacta de la lógica en generate_signal() y latest_signal().
    """
    close = latest_row.get("close")
    ema50 = latest_row.get("ema50")
    ema200 = latest_row.get("ema200")
    adx14 = latest_row.get("adx14", 0)
    rsi14 = latest_row.get("rsi14", 50)
    volume_ratio = latest_row.get("volume_ratio", 1)

    if close is None or ema50 is None or ema200 is None:
        return False
    if not (close > ema50 > ema200):
        return False
    if adx14 < ADX_MIN:
        return False
    if not (RSI_GATE[0] < rsi14 < RSI_GATE[1]):
        return False
    if volume_ratio < VR_MIN:
        return False
    return True


def overall_score(latest_row: pd.Series, regime_state: int = 0) -> float:
    """
    Score compuesto final para una fila (última barra).
    Combina factor_scores con pesos del régimen.
    """
    scores = factor_scores(latest_row)
    weights = CONTRACT.factor_weights.get(regime_state, CONTRACT.factor_weights[0])
    return sum(scores[f] * weights[f] for f in weights)


def signal_passes(latest_row: pd.Series, regime_state: int = 0) -> bool:
    """
    Verifica si una fila genera señal (eligible + score >= threshold).
    """
    if not is_eligible(latest_row):
        return False
    return overall_score(latest_row, regime_state) >= ENTRY_THRESHOLD


def frozen_echo() -> Dict:
    """Valores vigentes para auditoría/artefactos (eco del contrato)."""
    w = CONTRACT.factor_weights[0]
    return {
        "w_mom_runtime": w["momentum"],
        "w_rsi_runtime": w["rsi"],
        "entry_threshold": ENTRY_THRESHOLD,
        "rsi_score_band": list(RSI_SCORE_BAND),
        "rsi_gate": list(RSI_GATE),
        "adx_min": ADX_MIN,
        "vr_min": VR_MIN,
        "fuente": "signal_contract.py (CONTRATO ÚNICO B6)",
    }