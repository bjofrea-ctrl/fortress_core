"""
FASE 0b (v2) — BACKTEST CON COSTOS: V1-RANKING (b) vs BASELINE vs V1+FUND.

Misma spec de corrida que la v1 (mismos períodos, costos y métricas).
La v1 (blend sobre el gate, señal por bounds ±35) quedó archivada en
data/cache/backtest_v1_costs_20260810_083449.txt: bloqueó TODAS las
entradas (blend <= 0.5 < gate 0.6, matemático).

Variante (b) — decisión del usuario 2026-08-10: implementa EXACTAMENTE
lo que H7 validó en el OOS (calidad de RANKING, no de gate binario):
- El gate de entrada sigue usando el score técnico puro (sin V1).
- El ranking de oportunidades usa G2 = 0.5*rank(score técnico, pesos
  fijos) + 0.5*s_v1 con s_v1 = -rank(aaii) (ranking causal 260d, la
  señal pre-registrada en §7 — NO la normalización por bounds ±35 que
  usa el motor predictivo y que el 0b-v1 expuso como incompatible).
- Sin dato AAII -> s_v1 = 0 (neutro, el motor degrada a baseline).

Variante (f) — TRIAL #9 (0b-v2-fund), Fase 1, categoría fundamental:
- Mismo gate técnico puro y mismo ranking G3 = 0.5*rank(score técnico
  fijo) + 0.5*rank(score fundamental point-in-time del panel EDGAR).
- SIN componente AAII a propósito: la corrida difiere del baseline sólo
  en la pata fundamental, para aislar el efecto de la categoría (AAII ya
  tuvo su trial, el #8).
- Símbolos sin cobertura (SPY/QQQ, ETFs sin fundamentales): se rankean
  por score técnico puro.
- sue_score excluido pre-registrado (no derivable de EDGAR).

TRIAL #9 del conteo de n_trials del deflated Sharpe (conteo del
usuario): 5 variantes históricas documentadas en backtest_engine.py +
baseline-costos (0b-v1) + v1-gate (0b-v1) + v1-ranking (0b-v2) +
fundamentales (ésta, 0b-v2-fund).

Criterio de lectura (honesto, sin re-testear):
- Si el DSR de la variante (f) despega a significancia real -> hay
  edge. Si no -> respuesta honesta igual; mejor ahora que con plata.
"""
import os
import json
import datetime

import pandas as pd

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.edgar_fundamentals import _load_panel, compute_fundamental_score_series
from app.core.market_sentiment import build_sentiment_frame

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
START = "2019-01-01"
END = "2026-08-04"
DEVELOPMENT_END = "2024-12-31"
N_TRIALS = 9


def sentiment_map(trading_dates: pd.DatetimeIndex) -> dict:
    """Spread AAII crudo por fecha de trading (anti-lookahead: build_sentiment_frame
    ya aplica shift(1)+ffill). Sin dato -> no incluido (el motor degrada a neutro)."""
    sentiment = build_sentiment_frame(trading_dates)
    spread = sentiment["aaii_bullbear_spread"]
    return {ts: float(v) for ts, v in spread.items() if pd.notna(v)}


def fundamentals_map(price_data: dict) -> dict:
    """Score fundamental point-in-time por símbolo, alineado al índice de
    precios del backtest (ffill interno en compute_g3_rank_scores)."""
    panel = _load_panel()
    if panel is None:
        return {}
    out = {}
    for symbol in SYMBOLS:
        series = compute_fundamental_score_series(panel, symbol)
        if len(series) > 0:
            out[symbol] = series
    return out


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
    log("FASE 0b v2 — BACKTEST CON COSTOS: V1-RANKING (b) vs BASELINE vs V1+FUND (f)")
    log(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END} | comisión 0.10% + slippage 0.05% por lado")
    log(f"G2 = 0.5*rank(score fijo) + 0.5*(-rank(aaii)) | G3 = 0.5*rank(score fijo) + 0.5*rank(score fund) | DSR n_trials={N_TRIALS} (trial #9)")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)

    trading_dates = price_data["SPY"].index
    sent_map = sentiment_map(trading_dates)
    log(f"AAII disponible en {len(sent_map)}/{len(trading_dates)} días de trading")

    fund_map = fundamentals_map(price_data)
    log(f"Score fundamental point-in-time en {len(fund_map)}/{len(SYMBOLS)} símbolos (EDGAR panel)")

    log("\nCorriendo baseline (sin V1)...")
    res_base = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END)
    )

    log("Corriendo V1-ranking (b)...")
    res_v1 = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        sentiment_data=sent_map,
    )

    log("Corriendo V1+FUND (f, trial #9)...")
    res_fund = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        fundamentals_by_symbol=fund_map,
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
        mf = period_metrics(res_fund["equity_curve"], res_fund["trades"], s, e, engine)
        log(f"\n  {label}")
        log(f"    {'métrica':18s} {'baseline':>12s} {'V1':>12s} {'V1+F':>12s} {'Δ(F-base)':>12s}")
        for c in cols:
            b, v, f = mb.get(c, float("nan")), mv.get(c, float("nan")), mf.get(c, float("nan"))
            delta = f - b if isinstance(b, (int, float)) and isinstance(f, (int, float)) else float("nan")
            log(f"    {c:18s} {b:12.4f} {v:12.4f} {f:12.4f} {delta:+12.4f}")

    log("\n--- MONTE CARLO (bootstrap) ---")
    for label, res in [("baseline", res_base), ("V1", res_v1), ("V1+F", res_fund)]:
        boot = res["monte_carlo"].get("bootstrap", {})
        log(f"  {label:9s} mean={boot.get('mean', float('nan')):+.1f} p5={boot.get('p5', float('nan')):+.1f} "
            f"p95={boot.get('p95', float('nan')):+.1f} prob_loss={boot.get('prob_loss', float('nan')):.3f}")

    log("\n--- TRADES OOS 2025-2026 ---")
    for label, res in [("baseline", res_base), ("V1", res_v1), ("V1+F", res_fund)]:
        oos_trades = [t for t in res["trades"] if t["exit_date"].strftime("%Y-%m-%d") >= "2025-01-01"]
        wins = sum(1 for t in oos_trades if t["pnl"] > 0)
        log(f"  {label:9s} trades={len(oos_trades)}  wins={wins}  win_rate={wins / len(oos_trades) if oos_trades else float('nan'):.3f}")

    v1_trades = [t for t in res_v1["trades"] if t.get("g2_score") is not None]
    if v1_trades:
        g2_vals = pd.Series([t["g2_score"] for t in v1_trades])
        favored = [t for t in v1_trades if t["g2_score"] > 0.6]
        log(f"\n  V1-ranking: {len(v1_trades)}/{len(res_v1['trades'])} trades con g2_score "
            f"(media g2={g2_vals.mean():+.3f}, trades con g2>0.6 = {len(favored)})")
        for bucket, lo, hi in [("g2<=0.5", None, 0.5), ("0.5<g2<=0.7", 0.5, 0.7), ("g2>0.7", 0.7, None)]:
            sel = [t for t in v1_trades if (lo is None or t["g2_score"] > lo) and (hi is None or t["g2_score"] <= hi)]
            if len(sel) >= 5:
                wins = sum(1 for t in sel if t["pnl"] > 0)
                log(f"    {bucket:14s} n={len(sel):3d} win_rate={wins / len(sel):.3f} pnl_sum={sum(t['pnl'] for t in sel):+.0f}")

    fund_trades = [t for t in res_fund["trades"] if t.get("g3_score") is not None]
    if fund_trades:
        g3_vals = pd.Series([t["g3_score"] for t in fund_trades])
        favored = [t for t in fund_trades if t["g3_score"] > 0.6]
        log(f"\n  V1+F: {len(fund_trades)}/{len(res_fund['trades'])} trades con g3_score "
            f"(media g3={g3_vals.mean():+.3f}, trades con g3>0.6 = {len(favored)})")
        for bucket, lo, hi in [("g3<=0.5", None, 0.5), ("0.5<g3<=0.7", 0.5, 0.7), ("g3>0.7", 0.7, None)]:
            sel = [t for t in fund_trades if (lo is None or t["g3_score"] > lo) and (hi is None or t["g3_score"] <= hi)]
            if len(sel) >= 5:
                wins = sum(1 for t in sel if t["pnl"] > 0)
                log(f"    {bucket:14s} n={len(sel):3d} win_rate={wins / len(sel):.3f} pnl_sum={sum(t['pnl'] for t in sel):+.0f}")

    log("\n" + "=" * 72)
    log(f"Out: {out_path}")

    json_path = out_path.replace(".txt", ".json")
    with open(json_path, "w") as f:
        json.dump({
            "baseline": {"metrics_full": period_metrics(res_base["equity_curve"], res_base["trades"], START, END, engine)},
            "v1": {"metrics_full": period_metrics(res_v1["equity_curve"], res_v1["trades"], START, END, engine)},
            "v1_fund": {"metrics_full": period_metrics(res_fund["equity_curve"], res_fund["trades"], START, END, engine)},
        }, f, indent=2, default=str)


if __name__ == "__main__":
    main()
