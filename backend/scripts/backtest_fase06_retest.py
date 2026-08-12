"""
PLAN_MEJORA_MATEMATICA §0.6.1 — Re-test V1 (AAII) y fundamentales (EDGAR) sobre
universo 50, motor post-fix (2026-08-12). PRE-REGISTRADO antes de correr.

Contexto: trials #8/#9 corrieron sobre ejecución rota (PARTIAL_TP re-disparado,
52% filas shares=0) y universo 7. Este script repite la MISMA pregunta con el
motor actual (trial #10 fix + trial #11 piso de stop) y universo 50.

Variantes (sin cambios de hipótesis vs #8/#9):
  - baseline: sin variables externas.
  - V1-ranking: G2 = 0.5*rank(score técnico) + 0.5*(-rank(aaii)), gate técnico puro.
  - fundamentales: G3 = 0.5*rank(score técnico) + 0.5*rank(score fund EDGAR), sin AAII.

Criterio pre-registrado: DSR OOS >= 0.90 (n_trials=17, registro previo — re-test
barato, sin slot nuevo) en >= 2/3 ventanas evaluables (W1 2020-21, W2 2022-23,
W3 2024-2026-08-04, piso >= 30 trades). Revert automático: variante no adoptada
si no cumple (las variantes solo viven en este script).
"""
import datetime
import os

import pandas as pd

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.edgar_fundamentals import _load_panel, compute_fundamental_score_series
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


def sentiment_map(trading_dates: pd.DatetimeIndex) -> dict:
    sentiment = build_sentiment_frame(trading_dates)
    spread = sentiment["aaii_bullbear_spread"]
    return {ts: float(v) for ts, v in spread.items() if pd.notna(v)}


def fundamentals_map(price_data: dict) -> dict:
    panel = _load_panel()
    if panel is None:
        return {}
    out = {}
    for symbol in price_data:
        series = compute_fundamental_score_series(panel, symbol)
        if len(series) > 0:
            out[symbol] = series
    return out


def period_metrics(equity_curve, trades, s, e, engine):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=N_TRIALS), tr


def main():
    out_path = os.path.join("data", "cache",
                            f"fase06_retest_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("FASE 0.6 — RE-TEST V1 (AAII) y FUNDAMENTALES (EDGAR) — PRE-REGISTRADO")
    log(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END} | costos 0.15%/lado (0.10%+0.05%)")
    log("Motor actual: partial_done (trial #10) + piso de stop 0.05 (trial #11)")
    log(f"Ventanas: {', '.join(w[0] for w in WINDOWS)} | piso trades: {TRADE_FLOOR}")
    log(f"Criterio: DSR OOS >= 0.90 en >= 2/3 ventanas evaluables | N_TRIALS={N_TRIALS} (re-test, sin slot nuevo)")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)
    log(f"precios cargados: {len(price_data)} símbolos")

    trading_dates = price_data["SPY"].index
    sent_map = sentiment_map(trading_dates)
    log(f"AAII disponible en {len(sent_map)}/{len(trading_dates)} días de trading")

    fund_map = fundamentals_map(price_data)
    log(f"Score fundamental point-in-time en {len(fund_map)}/{len(price_data)} símbolos (EDGAR panel)")

    log("\nCorriendo baseline (50 símbolos, sin variables)...")
    res_base = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END)
    )

    log("Corriendo V1-ranking (G2 con AAII)...")
    res_v1 = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        sentiment_data=sent_map,
    )

    log("Corriendo fundamentales (G3 EDGAR, sin AAII)...")
    res_fund = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        fundamentals_by_symbol=fund_map,
    )

    engine = BacktestEngine(initial_capital=25000)
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    for label, s, e in WINDOWS:
        mb, trb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine)
        mv, trv = period_metrics(res_v1["equity_curve"], res_v1["trades"], s, e, engine)
        mf, trf = period_metrics(res_fund["equity_curve"], res_fund["trades"], s, e, engine)
        log(f"\n--- {label} (base n={len(trb)}, V1 n={len(trv)}, fund n={len(trf)}) ---")
        for c in cols:
            b, v, f = mb.get(c, float("nan")), mv.get(c, float("nan")), mf.get(c, float("nan"))
            log(f"    {c:18s} {b:12.4f} {v:12.4f} {f:12.4f}")

    log("\n--- TRADES POR VENTANA ---")
    for label, res in [("baseline", res_base), ("V1", res_v1), ("FUND", res_fund)]:
        for wlabel, s, e in WINDOWS:
            oos = [t for t in res["trades"] if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
            wins = sum(1 for t in oos if t["pnl"] > 0)
            evaluable = len(oos) >= TRADE_FLOOR
            log(f"  {label:8s} {wlabel:14s} trades={len(oos):3d} wins={wins:3d} "
                f"win_rate={wins / len(oos) if oos else float('nan'):.3f} evaluable={evaluable}")

    log("\n--- MONTE CARLO (bootstrap) ---")
    for label, res in [("baseline", res_base), ("V1", res_v1), ("FUND", res_fund)]:
        boot = res["monte_carlo"].get("bootstrap", {})
        log(f"  {label:8s} mean={boot.get('mean', float('nan')):+.1f} "
            f"p5={boot.get('p5', float('nan')):+.1f} p95={boot.get('p95', float('nan')):+.1f} "
            f"prob_loss={boot.get('prob_loss', float('nan')):.3f}")

    log("\n--- VEREDICTO vs CRITERIO (§0.6.1) ---")
    for vlabel, res in [("V1", res_v1), ("FUND", res_fund)]:
        passed = []
        for wlabel, s, e in WINDOWS:
            m, tr = period_metrics(res["equity_curve"], res["trades"], s, e, engine)
            ok_trades = len(tr) >= TRADE_FLOOR
            dsr = m.get("deflated_sharpe", float("nan"))
            ok_dsr = ok_trades and dsr >= 0.90
            passed.append(ok_dsr)
            log(f"  {vlabel:5s} {wlabel:14s} n={len(tr):3d} DSR={dsr:.4f} "
                f"{'PASA' if ok_dsr else 'no pasa'}{'' if ok_trades else ' (no evaluable)'}")
        log(f"  {vlabel}: {sum(passed)}/3 -> {'CUMPLE (re-ingresa a consideración)' if sum(passed) >= 2 else 'NO CUMPLE (refutación #8/#9 confirmada con vara arreglada)'}")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()