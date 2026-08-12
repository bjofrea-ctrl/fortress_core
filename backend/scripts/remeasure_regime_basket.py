"""
PLAN_MEJORA_MATEMATICA §11 regla 2 — RE-MEDICIÓN del condicionamiento de régimen
sobre la SERIE DEL BASKET (2026-08-11/12).

Contexto: el trial (a) basket usa el régimen HMM SOLO como identificador; el
ajuste de exposición por régimen (+0.198 GOLDILOCKS / -0.173 DEFLATION, "macro
contra-régimen", citado en RESUMEN_VALIDACION_VARIABLES §5 y PLAN_SENTIMIENTO)
NO entra al pre-registro hasta re-medirse con la especificación correcta.

La medición original (Fase 2) tenía DOS defectos que esta re-medición corrige:
  1. Target pooled sobre el panel de 50 acciones (cada fila por símbolo) — mezcla
     la dimensión temporal con la transversal. Acá el target es UN solo activo:
     el retorno forward del basket equal-weight de los 50.
  2. Régimen con lookahead (§3.1): cada fila recibía el régimen del último día de
     toda la serie. Acá el régimen se etiqueta walk-forward (decodificación Viterbi
     sobre [2015, t], fit HMM <= 2024-12-31) — sin usar fechas futuras.

Pregunta pre-registrada: ¿el patrón "macro contra-régimen" sobrevive sobre la serie
del basket con la spec limpia?

Criterio de decisión PRE-REGISTRADO (lección §10 — umbrales desde el inicio):
  El condicionamiento de régimen ENTRA al pre-registro si, sobre el basket y con
  régimen limpio, se conserva el patrón de signos de la medición original en los
  regímenes con muestra suficiente (n >= 200 días de basket):
     - GOLDILOCKS: IC macro significativo > 0  (era +0.198)
     - DEFLATION:  IC macro significativo < 0  (era -0.173)
  con |t| = |IC| * sqrt(n_eff) > 2.0 (Newey-West, mismo aparato que diagnose_sentiment_oos).
  Si un régimen cambia de signo, pierde significancia, o el IC es degenerado
  (n < 200), el condicionamiento NO entra y (a) corre SOLO con ADX.

El script NO decide nada por sí mismo: escribe el artefacto con huella timestamp y
la interpretación la hace el §11 del plan. Ver regla §3.4: todo número se verifica
contra el artefacto.
"""
import datetime
import os
import math

import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.predictive_engine import PredictiveEngine
from app.core.probabilistic_engine import SignalQualityMetrics
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX",
                 "DX-Y.NYB", "GC=F", "SI=F", "CL=F", "HG=F"]
FIT_END = "2024-12-31"
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE_DAYS = 5
MIN_BASKET_MEMBERS = 40     # piso de miembros del basket en la fecha
MIN_SAMPLE_PER_REGIME = 200  # piso de observaciones (días) por régimen
REGIME_SIGN_EXPECTED = {0: +1, 1: -1, 2: -1, 3: -1}  # GOLDILOCKS+, resto contra


def _norm_pvalue(z: float) -> float:
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def significance_threshold(n: int) -> float:
    return 2.0 / np.sqrt(n)


def newey_west_neff_1d(x: np.ndarray, y: np.ndarray, horizon: int, stride: int) -> float:
    """n_eff Newey-West para series 1D (un solo activo = basket)."""
    if len(x) != len(y):
        return 30.0
    n = len(x)
    if n < 30:
        return 30.0
    z = (x - x.mean()) * (y - y.mean())
    L = int(np.ceil(horizon / stride))
    lag_max = min(L, n - 2)
    if lag_max < 1:
        return max(float(n), 30.0)
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (L + 1)
    denom = 1 + 2 * np.sum(w * rho)
    return max(n / max(denom, 1 + L), 30.0)


def label_regimes_walk_forward(clf: GlobalRegimeClassifier, price_data: dict) -> pd.Series:
    """Etiqueta cada fecha del basket con su régimen, decodificando Viterbi sobre
    [inicio, t] (sin fechas futuras) — idéntico a audit_regime_hmm.py."""
    feats = clf._extract_features(price_data)
    dates = feats.index
    states = np.full(len(feats), -1, dtype=int)
    scaled_all = clf.scaler.transform(feats.values)
    for i in range(len(feats)):
        if i < 60:
            continue
        chunk = scaled_all[: i + 1]
        try:
            raw = clf.model.predict(chunk)
        except Exception:
            continue
        aligned = clf._align_states(raw, feats.iloc[: i + 1])
        states[i] = int(aligned[-1])
    return pd.Series(states, index=dates)


def build_basket_series(price_data: dict) -> pd.DataFrame:
    """Serie del basket equal-weight de los 50 símbolos (rebalanceo diario):
    retorno diario = media de retornos diarios de los miembros disponibles en la fecha.
    Devuelve columna 'basket' (nivel) y 'basket_ret' (retorno diario)."""
    closes = {s: d["close"] for s, d in price_data.items() if "close" in d and len(d) > 200}
    frame = pd.DataFrame(closes).sort_index()
    rets = frame.pct_change()
    # Piso de miembros: si faltan muchos, la fecha es de baja cobertura
    member_count = rets.notna().sum(axis=1)
    rets = rets.where(member_count >= MIN_BASKET_MEMBERS)
    basket_ret = rets.mean(axis=1).dropna()
    basket = (1 + basket_ret).cumprod()
    return pd.DataFrame({"basket": basket, "basket_ret": basket_ret})
