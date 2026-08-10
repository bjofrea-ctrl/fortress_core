"""Auditoría de la brecha señal->PnL (hipótesis de gap audit).

Corre UNA vez la configuración campeona (V1+FUND, trial #9) y vuelca a disco
todos los trades con win_prob calibrado, risk_events y equity curve, para
responder con datos reales del motor:

  H1: ¿la salida técnica corta ganadores antes del target 2:1?
  H2: ¿la calibración Platt (p) rechaza/selecciona mal los trades?
  H3: ¿cuánto del PnL se come el costo por lado?
"""
import datetime
import json
import os

import pandas as pd

from scripts.backtest_v1_costs import (
    SYMBOLS, MARKET_TICKERS, START, END,
    sentiment_map, fundamentals_map,
)
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe


def main():
    out_base = f"data/cache/audit_gap_exits_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    os.makedirs("data/cache", exist_ok=True)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)
    sent_map = sentiment_map(price_data["SPY"].index)
    fund_map = fundamentals_map(price_data)

    res = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        fundamentals_by_symbol=fund_map,
    )

    trades = pd.DataFrame(res["trades"])
    events = pd.DataFrame(res["risk_events"])
    equity = pd.DataFrame(res["equity_curve"])

    trades.to_parquet(out_base + "_trades.parquet")
    events.to_parquet(out_base + "_events.parquet")
    equity.to_parquet(out_base + "_equity.parquet")
    with open(out_base + "_meta.json", "w") as f:
        json.dump({"metrics": res["metrics"]}, f, indent=2, default=str)

    print(f"trades={len(trades)} events={len(events)} equity_days={len(equity)}")
    print(f"huella: {out_base}_*")


if __name__ == "__main__":
    main()
