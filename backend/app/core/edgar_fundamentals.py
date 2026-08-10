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
