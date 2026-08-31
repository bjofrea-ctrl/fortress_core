"""
A6.3 / screening_palas baseline recalculation (2026-08-28) — costo vigente.

Copia fiel de backend/scripts/backtest_baseline_clean.py con UN solo cambio
metodologico: se pasa explicitamente commission=0.0005 + slippage=0.0005
(0.10%/lado) a BacktestEngine.run(), que es el costo VIGENTE decidido en §33
(19/08). El baseline_clean_20260811 original corrio con los defaults VIEJOS
(commission=0.001 + slippage=0.0005 = 0.15%/lado), y por eso screening_palas.py
(A6.3) salio NO_INTERPRETABLE: hoy todo sale sistematicamente mejor por el
costo menor, no por un error de implementacion.

Mismo universo (SYMBOLS), ventanas (WINDOWS), N_TRIALS=17, TRADE_FLOOR=30,
START/END, y mismos parametros de motor que el script original. NO se edita
codigo de produccion y NO se sobreescribe baseline_clean_20260811_150643.txt
(queda como referencia historica del costo anterior).

El artefacto de salida usa timestamp de hoy (datetime.now en out_path).
"""
import datetime
import os

import pandas as pd

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.market_sentiment import build_sentiment_frame
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
START = "2019-01-01"
END = "2026-08-04"
N_TRIALS = 17
WINDOWS = [
    ("W1 2020-2021", "2020-01-01", "2021-12-31"),
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]
TRADE_FLOOR = 30

COMMISSION = 0.0005
SLIPPAGE = 0.0005


def period_metrics(equity_curve, trades, s, e, engine, n_trials):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=n_trials), tr


def main():
    out_path = os.path.join("data", "cache", f"baseline_clean_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("A6.3 / screening_palas — BASELINE RECALC (2026-08-28) con costo VIGENTE §33")
    log(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END} | costos 0.10%/lado (commission=0.0005, slippage=0.0005)")
    log("Motor: producción tal cual (commit de corrida abajo en git describe)")
    log(f"Ventanas: {', '.join(w[0] for w in WINDOWS)} | piso trades/ventana: {TRADE_FLOOR}")
    log(f"Criterio de los trials que usarán este baseline: DSR OOS >= 0.90 | N_TRIALS={N_TRIALS}")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)
    log(f"precios cargados: {len(price_data)} símbolos")

    trading_dates = price_data["SPY"].index
    sentiment = build_sentiment_frame(trading_dates)
    sent_map = {ts: float(v) for ts, v in sentiment["aaii_bullbear_spread"].items() if pd.notna(v)}
    log(f"AAII disponible en {len(sent_map)}/{len(trading_dates)} días de trading")

    log("\nCorriendo baseline (50 símbolos, sin V1)...")
    res_base = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        commission=COMMISSION, slippage=SLIPPAGE,
    )

    log("Corriendo V1-ranking (50 símbolos, G2 con AAII)...")
    res_v1 = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        sentiment_data=sent_map,
        commission=COMMISSION, slippage=SLIPPAGE,
    )

    pd.DataFrame(res_v1["trades"]).to_parquet(out_path.replace(".txt", "_trades.parquet"))
    pd.DataFrame(res_v1["risk_events"]).to_parquet(out_path.replace(".txt", "_events.parquet"))
    pd.DataFrame(res_v1["equity_curve"]).to_parquet(out_path.replace(".txt", "_equity.parquet"))

    engine = BacktestEngine(initial_capital=25000)
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    for label, s, e in WINDOWS:
        mb, trb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine, N_TRIALS)
        mv, trv = period_metrics(res_v1["equity_curve"], res_v1["trades"], s, e, engine, N_TRIALS)
        log(f"\n--- {label} (baseline n={len(trb)}, V1 n={len(trv)}) ---")
        for c in cols:
            b, v = mb.get(c, float("nan")), mv.get(c, float("nan"))
            log(f"    {c:18s} {b:12.4f} {v:12.4f}")

    log("\n--- TRADES POR VENTANA (V1) ---")
    for label, s, e in WINDOWS:
        oos = [t for t in res_v1["trades"] if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
        wins = sum(1 for t in oos if t["pnl"] > 0)
        evaluable = len(oos) >= TRADE_FLOOR
        log(f"  {label:14s} trades={len(oos):3d} wins={wins:3d} win_rate={wins / len(oos) if oos else float('nan'):.3f} evaluable={evaluable}")

    log("\n--- MONTE CARLO (bootstrap, V1) ---")
    boot = res_v1["monte_carlo"].get("bootstrap", {})
    log(f"  mean={boot.get('mean', float('nan')):+.1f} p5={boot.get('p5', float('nan')):+.1f} "
        f"p95={boot.get('p95', float('nan')):+.1f} prob_loss={boot.get('prob_loss', float('nan')):.3f}")

    log("\n--- VEREDICTO vs CRITERIO (informativo; este script NO decide nada) ---")
    passed = []
    for label, s, e in WINDOWS:
        mv, trv = period_metrics(res_v1["equity_curve"], res_v1["trades"], s, e, engine, N_TRIALS)
        ok_trades = len(trv) >= TRADE_FLOOR
        dsr = mv.get("deflated_sharpe", float("nan"))
        ok_dsr = ok_trades and dsr >= 0.90
        passed.append(ok_dsr)
        log(f"  {label:14s} n={len(trv):3d} DSR={dsr:.4f} {'PASA' if ok_dsr else 'no pasa'}"
            f"{'' if ok_trades else ' (no evaluable: < piso de trades)'}")
    log(f"\n  Ventanas que pasan: {sum(passed)}/3 -> criterio: {'CUMPLE' if sum(passed) >= 2 else 'NO CUMPLE'}")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
