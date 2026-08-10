"""
Cargador de fundamentales point-in-time desde el panel EDGAR local.

Prefiere el panel diario construido por scripts/build_fundamentals_panel.py
(data/cache/fundamentals_panel.parquet): ratios con fecha de filing REAL
(EDGAR) y precio local del día de trading siguiente — sin lookahead.

Si el panel no existe o no cubre el símbolo/fecha, degrada al sample
hardcodeado (SAMPLE_FUNDAMENTALS) y lo marca explícitamente en
_data_source, igual que el flujo Finnhub.
"""
import os
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd

PANEL_PATH = os.environ.get(
    "FUNDAMENTALS_PANEL_PATH", "data/cache/fundamentals_panel.parquet"
)

SAMPLE_FUNDAMENTALS = {
    "AAPL": {"pe_ratio": 35.2, "pb_ratio": 55.3, "ev_ebitda": 24.5, "roe": 147.9, "roa": 31.6,
             "debt_equity": 1.75, "fcf_yield": 0.6, "div_yield": 0.4, "eps_growth": 8.2,
             "gross_margin": 46.2, "peg": 2.8, "current_ratio": 0.9,
             "asset_turnover": 1.1, "book_value_growth": 12.1, "sue_score": 1.2},
    "MSFT": {"pe_ratio": 36.8, "pb_ratio": 13.5, "ev_ebitda": 25.2, "roe": 44.1, "roa": 18.2,
             "debt_equity": 0.42, "fcf_yield": 2.3, "div_yield": 0.7, "eps_growth": 15.8,
             "gross_margin": 69.8, "peg": 2.3, "current_ratio": 1.3,
             "asset_turnover": 0.6, "book_value_growth": 9.8, "sue_score": 2.1},
    "NVDA": {"pe_ratio": 60.5, "pb_ratio": 45.2, "ev_ebitda": 40.1, "roe": 115.0, "roa": 65.4,
             "debt_equity": 0.25, "fcf_yield": 1.1, "div_yield": 0.03, "eps_growth": 89.3,
             "gross_margin": 75.8, "peg": 0.68, "current_ratio": 2.5,
             "asset_turnover": 0.9, "book_value_growth": 35.4, "sue_score": 3.5},
    "AMZN": {"pe_ratio": 38.9, "pb_ratio": 8.1, "ev_ebitda": 18.9, "roe": 22.3, "roa": 6.5,
             "debt_equity": 0.62, "fcf_yield": 0.8, "div_yield": 0.0, "eps_growth": 30.1,
             "gross_margin": 47.1, "peg": 1.3, "current_ratio": 1.0,
             "asset_turnover": 1.3, "book_value_growth": 20.5, "sue_score": 2.8},
    "GOOGL": {"pe_ratio": 26.1, "pb_ratio": 7.2, "ev_ebitda": 16.8, "roe": 30.5, "roa": 15.9,
              "debt_equity": 0.08, "fcf_yield": 3.2, "div_yield": 0.5, "eps_growth": 18.4,
              "gross_margin": 59.7, "peg": 1.4, "current_ratio": 2.2,
              "asset_turnover": 0.7, "book_value_growth": 13.2, "sue_score": 1.8},
    "SPY": {"pe_ratio": 26.5, "pb_ratio": 4.8, "ev_ebitda": 18.2, "roe": 19.8, "roa": 8.5,
            "debt_equity": 1.1, "fcf_yield": 2.5, "div_yield": 1.2, "eps_growth": 6.8,
            "gross_margin": 35.0, "peg": 3.9, "current_ratio": 1.0,
            "asset_turnover": 0.5, "book_value_growth": 5.8, "sue_score": 0.5},
}

RATIO_COLS = [
    "pe_ratio", "pb_ratio", "ev_ebitda", "roe", "roa", "debt_equity",
    "fcf_yield", "div_yield", "eps_growth", "gross_margin", "peg",
    "current_ratio", "asset_turnover", "book_value_growth", "sue_score",
]

# Especificaciones del blend de fundamentales del motor (_fundamental_signals
# en predictive_engine.py): (columna, lo, hi, dirección, peso, modo).
# sue_score EXCLUIDO pre-registrado (no derivable de EDGAR: requiere
# expectativas de consenso de analistas).
_FUND_SPECS = [
    ("pe_ratio", 5, 60, "invert", 0.12, "neg_eps"),
    ("pb_ratio", 0.5, 10, "invert", 0.12, "positive"),
    ("ev_ebitda", 3, 30, "invert", 0.08, "positive"),
    ("roe", -5, 30, "asis", 0.12, None),
    ("roa", -3, 15, "asis", 0.08, None),
    ("debt_equity", 0, 3, "invert", 0.10, None),
    ("fcf_yield", -2, 10, "asis", 0.12, None),
    ("div_yield", 0, 6, "asis", 0.06, None),
    ("eps_growth", -20, 50, "asis", 0.15, None),
    ("gross_margin", 10, 60, "asis", 0.12, None),
    ("peg", 0, 3, "invert", 0.05, "positive"),
    ("current_ratio", 0.5, 3, "asis", 0.04, None),
    ("asset_turnover", 0, 2, "asis", 0.04, None),
    ("book_value_growth", -10, 30, "asis", 0.04, "damp"),
]

_panel_cache: Optional[pd.DataFrame] = None


def _load_panel() -> Optional[pd.DataFrame]:
    global _panel_cache
    if _panel_cache is not None:
        return _panel_cache
    if not os.path.exists(PANEL_PATH):
        return None
    try:
        p = pd.read_parquet(PANEL_PATH)
        if p.index.names == ["date", "symbol"]:
            p = p.reset_index()
        p["date"] = pd.to_datetime(p["date"])
        p = p.sort_values("date")
        _panel_cache = p
        return p
    except Exception:
        return None


def compute_fundamental_score_series(
    panel: pd.DataFrame, symbol: str
) -> pd.Series:
    """Score fundamental continuo en [-1, +1] por día, replicando el blend
    de _fundamental_signals del motor predictivo (mismos pesos,
    normalizaciones y direcciones) sobre el panel point-in-time.

    - Fidelidad al motor: componente activo si el ratio existe y es != 0
      (equivalente al check `if f.get(col)` del motor con dicts EDGAR,
      donde NaN llega como None). sue_score no participa (pre-registrado).
    - Denominador por día = suma de pesos de componentes activos; sin
      componentes activos -> 0.0 (igual que el motor con dict vacío).
    """
    import numpy as np

    sub = panel[panel["symbol"] == symbol.upper()].set_index("date").sort_index()
    if sub.empty:
        return pd.Series(dtype=float)

    numer = pd.Series(0.0, index=sub.index)
    denom = pd.Series(0.0, index=sub.index)

    for col, lo, hi, direction, weight, mode in _FUND_SPECS:
        if col not in sub.columns:
            continue
        raw = sub[col].astype(float)
        active = raw.notna() & (raw != 0.0)
        normed = ((raw - lo) / (hi - lo) * 2 - 1).clip(-1, 1)

        if mode == "neg_eps":
            signal = pd.Series(
                np.where(raw > 0, -normed, np.where(raw < 0, -0.8, 0.0)),
                index=sub.index,
            )
        elif mode == "positive":
            signal = pd.Series(np.where(raw > 0, -normed, 0.0), index=sub.index)
        else:
            signal = normed.where(active, 0.0)
        if mode == "damp":
            signal = signal * 0.7

        numer = numer + signal.fillna(0.0) * weight
        denom = denom + active.astype(float) * weight

    score = numer.div(denom).fillna(0.0).clip(-1, 1)
    return score


def get_edgar_fundamentals(
    symbol: str, as_of: Optional[date] = None
) -> Optional[Dict]:
    """Ratios point-in-time del panel EDGAR para symbol en la fecha as_of
    (último día <= as_of). None si el panel no cubre el símbolo."""
    panel = _load_panel()
    if panel is None:
        return None
    symbol = symbol.upper()
    sub = panel[panel["symbol"] == symbol]
    if len(sub) == 0:
        return None
    if as_of is None:
        as_of = datetime.now().date()
    mask = sub["date"] <= pd.Timestamp(as_of)
    if not mask.any():
        return None
    row = sub.loc[mask].iloc[-1]
    out = {}
    for col in RATIO_COLS:
        v = row.get(col)
        out[col] = None if pd.isna(v) else float(v)
    return out


def get_fundamentals(
    symbol: str, as_of: Optional[date] = None
) -> Optional[Dict]:
    """Resolución: panel EDGAR -> sample hardcodeado (marcado)."""
    edgar = get_edgar_fundamentals(symbol, as_of)
    if edgar is not None:
        edgar["_data_source"] = "edgar_point_in_time"
        return edgar
    data = SAMPLE_FUNDAMENTALS.get(symbol.upper())
    if data is None:
        return None
    return {**data, "_data_source": "sample_hardcoded_not_live"}
