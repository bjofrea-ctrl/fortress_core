"""
FASE 0b — BACKTEST CON COSTOS: V1 vs BASELINE (SPEC CONGELADA).

Pregunta pre-registrada (PLAN_MEJORA): ¿la integración V1 (AAII, blend
0.50) mejora el desempeño NETO (con costos) sobre el universo real?

Spec (UNA corrida por variante, no se re-testea):
- Universo: SPY/QQQ/AAPL/MSFT/GOOGL/AMZN/NVDA, 2019-01-01 a 2026-08-04.
- Costos: comisión 0.10% + slippage 0.05% por lado (defaults del motor).
- Señal V1: s_v1 = -clip((spread+35)/70, 0, 1) — misma definición que
  sentiment_regime.py (AAII_SPREAD_BOUND=35). Alineación anti-lookahead
  con build_sentiment_frame (shift(1) + ffill). Sin dato AAII -> None
  -> baseline puro (igual que el motor degrada).
- Blend: 0.5*técnico + 0.5*s_v1 antes del gate de entrada y del ranking.
- DSR: n_trials=7 — las 5 variantes históricas documentadas en
  backtest_engine.py + las 2 comparadas en esta corrida.
- Métricas por período: full (2019-2026), desarrollo (2019-2024), OOS
  (2025-2026).
- Limitación declarada: la calibración Platt se entrena con scores sin
  V1 (el histórico AAII empieza 2019-10, el dataset de calibración va
  hasta 2018); con V1 el win_prob (Kelly) usa un mapeo entrenado en
  scores puros — sesgo conocido, aceptado para esta corrida.
"""
import os
import json
import datetime

import pandas as pd

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.market_sentiment import build_sentiment_frame

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
START = "2019-01-01"
END = "2026-08-04"
DEVELOPMENT_END = "2024-12-31"
N_TRIALS = 7
AAII_BOUND = 35.0


def s_v1_series(trading_dates: pd.DatetimeIndex) -> dict:
    sentiment = build_sentiment_frame(trading_dates)
    spread = sentiment["aaii_bullbear_spread"]
    s_v1 = -(spread + AAII_BOUND).clip(0, 2 * AAII_BOUND) / (2 * AAII_BOUND)
    return {ts: float(v) for ts, v in s_v1.items() if pd.notna(v)}


def period_metrics(equity_curve, trades, start: str, end: str, engine: BacktestEngine) -> dict:
    eq = [p for p in equity_curve if start <= p["date"].strftime("%Y-%m-%d") <= end]
    tr = [t for t in trades if start <= t["exit_date"].strftime("%Y-%m-%d") <= end]
    if not eq:
        return {"error": "sin equity_curve en el período"}
    return engine.calculate_metrics(eq, tr, n_trials=N_TRIALS)


def main():
    out_path = os.path.join("data", "cache", f"backtest_v1_costs_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("FASE 0b — BACKTEST CON COSTOS: V1 vs BASELINE (spec congelada)")
    log(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END} | comisión 0.10% + slippage 0.05% por lado")
    log(f"Blend V1: 0.50 fijo | s_v1 = -clip((spread+35)/70, 0, 1) | DSR n_trials={N_TRIALS}")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)

    trading_dates = price_data["SPY"].index
    sentiment_map = s_v1_series(trading_dates)
    log(f"AAII disponible en {len(sentiment_map)}/{len(trading_dates)} días de trading")

    log("\nCorriendo baseline (sin V1)...")
    res_base = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END)
    )

    log("Corriendo V1 (blend 0.50)...")
    res_v1 = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        sentiment_scores=sentiment_map,
    )

    engine = BacktestEngine(initial_capital=25000)
    periods = [
        ("FULL 2019-2026", START, END),
        ("DESARROLLO 2019-2024", START, DEVELOPMENT_END),
        ("OOS 2025-2026", "2025-01-01", END),
    ]
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    log("\n--- MÉTRICAS POR PERÍODO ---")
    for label, s, e in periods:
        mb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine)
        mv = period_metrics(res_v1["equity_curve"], res_v1["trades"], s, e, engine)
        log(f"\n  {label}")
        log(f"    {'métrica':18s} {'baseline':>12s} {'V1':>12s} {'Δ':>12s}")
        for c in cols:
            b, v = mb.get(c, float("nan")), mv.get(c, float("nan"))
            delta = v - b if isinstance(b, (int, float)) and isinstance(v, (int, float)) else float("nan")
            log(f"    {c:18s} {b:12.4f} {v:12.4f} {delta:+12.4f}")

    log("\n--- MONTE CARLO (bootstrap) ---")
    for label, res in [("baseline", res_base), ("V1", res_v1)]:
        boot = res["monte_carlo"].get("bootstrap", {})
        log(f"  {label:9s} mean={boot.get('mean', float('nan')):+.1f} p5={boot.get('p5', float('nan')):+.1f} "
            f"p95={boot.get('p95', float('nan')):+.1f} prob_loss={boot.get('prob_loss', float('nan')):.3f}")

    log("\n--- TRADES OOS 2025-2026 ---")
    for label, res in [("baseline", res_base), ("V1", res_v1)]:
        oos_trades = [t for t in res["trades"] if t["exit_date"].strftime("%Y-%m-%d") >= "2025-01-01"]
        wins = sum(1 for t in oos_trades if t["pnl"] > 0)
        log(f"  {label:9s} trades={len(oos_trades)}  wins={wins}  win_rate={wins / len(oos_trades) if oos_trades else float('nan'):.3f}")

    v1_trades = [t for t in res_v1["trades"] if "sentiment_v1" in t.get("factors", {})]
    if v1_trades:
        spreads_used = [t["factors"]["sentiment_v1"] for t in v1_trades]
        log(f"\n  V1: {len(v1_trades)}/{len(res_v1['trades'])} trades con factor V1 activo "
            f"(media s_v1={pd.Series(spreads_used).mean():+.3f})")

    log("\n" + "=" * 72)
    log(f"Out: {out_path}")

    json_path = out_path.replace(".txt", ".json")
    with open(json_path, "w") as f:
        json.dump({
            "baseline": {"metrics_full": period_metrics(res_base["equity_curve"], res_base["trades"], START, END, engine)},
            "v1": {"metrics_full": period_metrics(res_v1["equity_curve"], res_v1["trades"], START, END, engine)},
        }, f, indent=2, default=str)


if __name__ == "__main__":
    main()
