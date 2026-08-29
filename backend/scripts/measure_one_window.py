"""Medicion rapida: solo W1 POOLED para estimar pico sin 60min de espera."""
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe

PALA = ["NVDA", "AVGO", "QCOM", "MSFT", "ORCL", "CSCO"]
MACRO = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]

def main():
    print("[measure] cargando universo...")
    full_price = load_universe(SYMBOLS, "2016-01-01", "2026-08-14")
    market_data = load_universe(MACRO, "2016-01-01", "2026-08-14")
    pooled = dict(full_price)
    print(f"[measure] POOLED N={len(pooled)} W1 2020-01-01->2021-12-31")
    eng = BacktestEngine(initial_capital=25000)
    res = eng.run(pooled, market_data, pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31"), commission=0.0005, slippage=0.0005, execution_lag_days=1)
    print(f"[measure] W1 done S={res['metrics']['sharpe_ratio']:.4f} D={res['metrics']['deflated_sharpe']:.4f} n={res['metrics']['total_trades']}")
    print("[measure] DONE")

if __name__ == "__main__":
    main()
