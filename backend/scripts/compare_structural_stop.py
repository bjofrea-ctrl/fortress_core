"""
T1.4 (PLAN_INTEGRACION_INDICAGENT.md) — Backtest A/B: stop/target estructural
vs. baseline ATR, sobre el MISMO período.

Criterio de aceptación 4 del ticket: correr un backtest A/B (con y sin
market_structure) y comparar métricas. NO promociona nada a default — solo
documenta el comparativo. La promoción requiere trial pre-registrado propio
(regla no negociable del repo).

Misma data, mismas fechas, misma semilla implícita (el motor es determinista);
la ÚNICA diferencia entre ambas corridas es use_market_structure=True/False,
que cambia: resolución de stop/target en generate_signal y la puerta RR>=MIN_RR.

Output: data/cache/compare_structural_stop_<ts>.txt
"""
import datetime
import os
import sys
from datetime import datetime as dt

import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe

# Período configurable por argv: python -m scripts.compare_structural_stop 2021-01-01 2023-12-31
# y armada: ... baseline | estructural | both (default both) — para correr en paralelo.
DEFAULT_START, DEFAULT_END = "2020-01-01", "2026-07-31"
START = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_START
END = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_END
ARM = sys.argv[3] if len(sys.argv) > 3 else "both"
ARMS = {
    "baseline": [("baseline (ATR puro)", False)],
    "estructural": [("estructural (T1.4)", True)],
    "both": [("baseline (ATR puro)", False), ("estructural (T1.4)", True)],
}
RUN_ARMS = ARMS[ARM]
MACRO = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:+.4f}"
    return str(v)


def main() -> int:
    out_path = os.path.join(
        "data", "cache",
        f"compare_structural_stop_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    lines = []

    def out(msg: str = ""):
        lines.append(msg)
        print(msg)

    out("=" * 78)
    out("T1.4 — A/B backtest: stop/target estructural vs baseline ATR (mismo período)")
    out(f"Período: {START} → {END} | Universo: {len(SYMBOLS)} | Capital: 25000")
    out("=" * 78)

    price_data = load_universe(SYMBOLS, "2016-01-01", END)
    market_data = load_universe(MACRO, "2016-01-01", END)

    start_dt = dt(*pd.Timestamp(START).timetuple()[:3])
    end_dt = dt(*pd.Timestamp(END).timetuple()[:3])

    results = {}
    rr_logs = {}
    for label, use_ms in RUN_ARMS:
        engine = BacktestEngine(initial_capital=25000)
        # RR medio: captura no invasiva del payoff_ratio teórico de las señales
        # emitidas en el loop principal (date >= start). La recalibración previa
        # (< start) y los refits walk-forward durante el loop re-emiten señales
        # SIN el kwarg market_structure (payoff 2.0) que NO son decisiones reales;
        # el loop principal SIEMPRE pasa market_structure= (aunque sea None en la
        # armada baseline) -> la presencia del kwarg aísla las decisiones reales.
        logged = []
        _orig = engine.signal_engine.generate_signal
        def _wrapped(*args, **kwargs):
            sig = _orig(*args, **kwargs)
            if (sig is not None and sig["date"] >= pd.Timestamp(START)
                    and "market_structure" in kwargs):
                logged.append((sig["date"], sig["structural_resolution"],
                               sig["payoff_ratio"], sig["score"]))
            return sig
        engine.signal_engine.generate_signal = _wrapped

        out(f"\nCorriendo: {label} ...")
        t0 = datetime.datetime.now()
        res = engine.run(price_data, market_data, start_dt, end_dt,
                         commission=0.001, slippage=0.0005,
                         execution_lag_days=1,
                         use_market_structure=use_ms)
        elapsed = (datetime.datetime.now() - t0).total_seconds()
        out(f"  terminado en {elapsed:.1f}s | trades={res['metrics'].get('total_trades', 0)}")
        results[label] = res
        rr_logs[label] = logged

    # Tabla comparativa de métricas (1 o 2 armadas)
    arms = list(results.keys())
    has_both = len(arms) == 2
    out("\n" + "=" * 78)
    if has_both:
        out(f"{'métrica':22s} {'baseline (ATR)':>16s} {'estructural (T1.4)':>20s} {'Δ':>10s}")
    else:
        out(f"{'métrica':22s} {arms[0]:>36s}")
    out("-" * 78)
    ma = results[arms[0]]["metrics"]
    mb = results[arms[1]]["metrics"] if has_both else {}
    for key in ("cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown",
                "calmar_ratio", "win_rate", "profit_factor", "total_trades",
                "deflated_sharpe"):
        va = ma.get(key, float("nan"))
        if has_both:
            vb = mb.get(key, float("nan"))
            if key == "profit_factor":
                va_s = f"{va:.3f}" if isinstance(va, float) else str(va)
                vb_s = f"{vb:.3f}" if isinstance(vb, float) else str(vb)
                delta = "?"
            elif key == "total_trades":
                va_s, vb_s, delta = str(va), str(vb), str(vb - va)
            else:
                va_s, vb_s = _fmt(float(va)), _fmt(float(vb))
                delta = _fmt(float(vb) - float(va))
            out(f"{key:22s} {va_s:>16s} {vb_s:>20s} {delta:>10s}")
        else:
            va_s = f"{va:.4f}" if key != "total_trades" else str(va)
            out(f"{key:22s} {va_s:>36s}")

    # RR medio de las señales emitidas (payoff teórico post-puerta)
    out("\n" + "=" * 78)
    out(f"{'métrica':22s} {'baseline (ATR)':>16s} {'estructural (T1.4)':>20s}")
    out("-" * 78)
    for name, logs in rr_logs.items():
        n_sig = len(logs)
        mean_rr = float(pd.Series([r[2] for r in logs]).mean()) if n_sig else float("nan")
        n_struct = sum(1 for r in logs if r[1])
        mean_score = float(pd.Series([r[3] for r in logs]).mean()) if n_sig else float("nan")
        out(f"{name:22s} señales={n_sig:4d} RR_medio={mean_rr:.3f} n_struct={n_struct} score_medio={mean_score:.3f}")

    # Trades: resumen por armada
    out("\n" + "=" * 78)
    out("Resumen de trades (todas las entradas del período):")
    for name, res in results.items():
        tr = res["trades"]
        wins = [t for t in tr if t["pnl"] > 0]
        avg_pnl = float(pd.Series([t["pnl"] for t in tr]).mean()) if tr else float("nan")
        total_pnl = float(sum(t["pnl"] for t in tr)) if tr else 0.0
        out(f"  {name:22s} trades={len(tr):4d} wins={len(wins):4d} "
            f"win_rate={len(wins)/len(tr) if tr else float('nan'):.3f} "
            f"avg_pnl={avg_pnl:+.2f} total_pnl={total_pnl:+.2f}")

    out("\nNOTA: este A/B es INFORMATIVO, no decisional. La promoción o no de")
    out("stop estructural a default requiere trial pre-registrado propio con la")
    out("misma disciplina que el resto del proyecto. MIN_RR=1.5 es default del")
    out("ticket, no validado empíricamente.")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nOut: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
