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

START = "2020-01-01"
END = "2026-07-31"
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
    for label, use_ms in (("baseline (ATR puro)", False),
                          ("estructural (T1.4)", True)):
        engine = BacktestEngine(initial_capital=25000)
        out(f"\nCorriendo: {label} ...")
        t0 = datetime.datetime.now()
        res = engine.run(price_data, market_data, start_dt, end_dt,
                         commission=0.001, slippage=0.0005,
                         execution_lag_days=1,
                         use_market_structure=use_ms)
        elapsed = (datetime.datetime.now() - t0).total_seconds()
        out(f"  terminado en {elapsed:.1f}s | trades={res['metrics'].get('total_trades', 0)}")
        results[label] = res

    # Tabla comparativa de métricas
    out("\n" + "=" * 78)
    out(f"{'métrica':22s} {'baseline (ATR)':>16s} {'estructural (T1.4)':>20s} {'Δ':>10s}")
    out("-" * 78)
    a = results["baseline (ATR puro)"]["metrics"]
    b = results["estructural (T1.4)"]["metrics"]
    for key in ("cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown",
                "calmar_ratio", "win_rate", "profit_factor", "total_trades",
                "deflated_sharpe"):
        va, vb = a.get(key, float("nan")), b.get(key, float("nan"))
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
