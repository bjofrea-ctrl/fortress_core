"""
PLAN_MEJORA_MATEMATICA §11 — TRIAL (a): timing sobre basket único con score ADX
(2026-08-11). PREREGISTRADO antes de correr (este archivo + §11 del plan).

Regla (fijada según §11, decisiones 1 y 2 del pre-registro):
  - Activo: basket equal-weight de los 50 símbolos del universo (rebalanceo
    diario, mismo universo/ventana/costos que el baseline). SPY solo sanity
    observacional, NO decide.
  - Score de timing: ADX(14) del basket, con los MISMO umbrales absolutos del
    motor (signal_engine.py:102-103, 128): LONG si ADX>25 (adx_score 0.9),
    FLAT/exit si ADX<20 (gate <20 no compra), tramo 20-25 mantiene estado
    (histéresis, adx_score 0.3). Chequeo de distribución previo confirmó
    (basket_adx_dist_20260811_214847.txt) que la distribución NO está
    degenerada -> no se recalibra por percentil.
  - Régimen: NO condiciona (re-medición §11 regla 2 no sobrevivió -> fuera).
  - Costos: 0.15%/lado (commission 0.001 + slippage 0.0005), igual baseline.
  - Producción NO tocada: script independiente, reversión al borrar.

Criterio (congelado): DSR OOS >= 0.90 en >= 2/3 ventanas (W1 2020-2021,
W2 2022-2023, W3 2024-2026), piso >= 30 trades/ventana, N_TRIALS=17+1=18.
Si basket+ADX supera el baseline oficial (baseline_clean_20260811_150643.txt)
en DSR en 2/3 ventanas -> (a) gana; si no -> (a) descartada como (b)/(c).
"""
import datetime
import os

import numpy as np
import pandas as pd

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
MIN_BASKET_MEMBERS = 40
WARMUP_DAYS = 30
N_TRIALS = 18
TRADE_FLOOR = 30
INITIAL_CAPITAL = 25000.0
COST_PER_SIDE = 0.001 + 0.0005  # commission + slippage = 0.15%/lado
LONG_ABOVE = 25.0
FLAT_BELOW = 20.0
WINDOWS = [
    ("W1 2020-2021", "2020-01-01", "2021-12-31"),
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]
BASELINE_ARTIFACT = "data/cache/baseline_clean_20260811_150643.txt"


def build_basket_series(price_data: dict) -> pd.DataFrame:
    """Serie del basket equal-weight (rebalanceo diario), MISMA construcción
    que la re-medición de régimen y el chequeo de distribución."""
    closes = {s: d["close"] for s, d in price_data.items() if "close" in d and len(d) > 200}
    frame = pd.DataFrame(closes).sort_index()
    rets = frame.pct_change()
    member_count = rets.notna().sum(axis=1)
    rets = rets.where(member_count >= MIN_BASKET_MEMBERS)
    basket_ret = rets.mean(axis=1).dropna()
    basket = (1 + basket_ret).cumprod()
    basket = basket / basket.iloc[0] * INITIAL_CAPITAL  # nivel en unidades de capital
    return pd.DataFrame({"basket": basket, "basket_ret": basket_ret})


def adx_series(close: pd.Series) -> pd.Series:
    """ADX(14) de Wilder sobre el cierre del basket (high=low=close)."""
    high = low = close
    plus_dm = high.diff().clip(lower=0)
    minus_dm = -low.diff().clip(upper=0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1
    ).max(axis=1)
    atr_ = tr.rolling(window=14).mean()
    plus_di = 100 * plus_dm.rolling(window=14).mean() / atr_
    minus_di = 100 * minus_dm.rolling(window=14).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(window=14).mean()


def period_metrics(equity_curve, trades, s, e, engine, n_trials):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=n_trials), tr
