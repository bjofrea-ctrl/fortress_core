"""Impacto del lag de ejecución (T0.2): lag=0 (bug, misma barra) vs lag=1 (open siguiente).

Mide Sharpe/CAGR/max_dd sobre el mismo universo/periodo con los dos lags.
Universo chico y periodo corto para que corra rápido — no todo el universo 50.
"""
import datetime

from app.core.backtest_engine import BacktestEngine

CACHE = "data/cache"


def load(symbols, start, end):
    import pandas as pd
    out = {}
    for s in symbols:
        try:
            df = pd.read_parquet(f"{CACHE}/{s}.parquet")
            df.columns = [str(c).lower() for c in df.columns]
            df = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
            if len(df) > 220:
                out[s] = df
        except FileNotFoundError:
            continue
    return out


PRICE = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "NVDA", "AMZN"]
MARKET = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]

START, END = "2021-01-01", "2023-12-31"

price_data = load(PRICE, "2019-01-01", END)
market_data = load(MARKET, "2015-01-01", END)
print(f"price symbols: {sorted(price_data)}")
print(f"market symbols: {sorted(market_data)}")


def show(lag):
    engine = BacktestEngine(initial_capital=25000)
    res = engine.run(price_data, market_data, datetime.datetime(2021, 1, 1),
                     datetime.datetime(2023, 12, 31), execution_lag_days=lag)
    m = res["metrics"]
    print(f"--- lag={lag} ---")
    print(f"  n_trades={m['total_trades']}  CAGR={m['cagr']:.4f}  Sharpe={m['sharpe_ratio']:.4f}  "
          f"max_dd={m['max_drawdown']:.4f}  win_rate={m['win_rate']:.3f}  deflated_sharpe={m['deflated_sharpe']:.4f}")
    return m


m0 = show(0)
m1 = show(1)
print("\n=== DELTA (lag1 - lag0) ===")
for k in ["total_trades", "cagr", "sharpe_ratio", "max_drawdown", "win_rate", "deflated_sharpe"]:
    if isinstance(m0.get(k), float) and isinstance(m1.get(k), float):
        print(f"  {k}: {m1[k] - m0[k]:+.4f}")
