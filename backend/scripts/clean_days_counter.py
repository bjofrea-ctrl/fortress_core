#!/usr/bin/env python3
"""
CLI del contador automático de días limpios del gate de 60 días (A2).

PLAN_REMEDIO_BRECHAS_20260903.md §A2 — corre al final de la fase 22:10 ET
(después del decide del último hábil del mes, que es cuando el reconciler
A1 ya cerró las huérfanas). Lee los logs canónicos del pipeline + updater
y `pipeline_state.json`, evalúa las 3 condiciones del gate para cada día
hábil desde GATE_START_DATE hasta hoy (inclusivos), y persiste el record
en `backend/data/clean_days.json`.

Idempotente: re-correrlo solo SOBREESCRIBE el JSON (la "racha" reflejará
siempre la ventana completa hasta hoy, no se acumula entre corridas —
los días viejos que ya eran limpios siguen siéndolo).

Uso:
    cd backend && python -m scripts.clean_days_counter            # run normal
    python -m scripts.clean_days_counter --print                 # run + imprime resumen
    python -m scripts.clean_days_counter --today 2026-12-01      # simula fecha (tests)
    python -m scripts.clean_days_counter --dry-run               # NO escribe el JSON
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from typing import Optional

# A2 (PLAN_REMEDIO_BRECHAS_20260903.md §A2): el contador vive en core para
# ser reusable y testeable sin red. El wrapper solo hace I/O.
from app.core.clean_days import (
    CLEAN_DAYS_PATH,
    GATE_START_DATE,
    _trading_days_calendar,
    evaluate_window,
    load_state,
    make_record,
    read_text,
    write_record,
)


def _print_summary(record: dict, out=sys.stdout) -> None:
    print(f"[A2] gate_start = {record['gate_start']}", file=out)
    print(f"[A2] last_evaluated = {record['last_evaluated']}", file=out)
    print(f"[A2] streak = {record['streak']}", file=out)
    if record["streak_started"]:
        print(f"[A2] streak_started = {record['streak_started']}", file=out)
    print(f"[A2] n_clean = {record['n_clean']} / n_total = {record['n_total']}", file=out)
    # Mostrar los últimos 5 días para auditoría rápida.
    last5 = record["days"][-5:]
    for d in last5:
        ev = d["evidence"]
        a = "OK" if ev["a_pipeline_rc0"]["rc_ok"] else "FAIL"
        b = "OK" if ev["b_updater_no_precios_error"]["present"] else "FAIL"
        c = ev["c_reconcile_unexplained_zero"]["verdict"]
        flag = " " if d["clean"] else "X"
        print(
            f"  {flag} {d['date']}  a={a} b={b} c={c}"
            + (f"  reasons={'|'.join(d['reasons'])}" if d["reasons"] else ""),
            file=out,
        )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--today", type=str, default=None,
        help="YYYY-MM-DD — simula la fecha de evaluación (default: hoy)",
    )
    parser.add_argument(
        "--pipeline-log", default=__import__("os").path.join("..", "scripts", "pipeline_diario.log"),
        help="Path al log del pipeline (default: ../scripts/pipeline_diario.log)",
    )
    parser.add_argument(
        "--updater-log", default=__import__("os").path.join("..", "scripts", "data_updater.log"),
        help="Path al log del updater (default: ../scripts/data_updater.log)",
    )
    parser.add_argument(
        "--state", default=__import__("os").path.join("data", "cache", "pipeline_state.json"),
        help="Path a pipeline_state.json",
    )
    parser.add_argument(
        "--output", default=CLEAN_DAYS_PATH,
        help=f"Path de salida (default: {CLEAN_DAYS_PATH})",
    )
    parser.add_argument(
        "--print", action="store_true",
        help="Imprime resumen del record a stdout",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calcula pero NO escribe el JSON en disco",
    )
    args = parser.parse_args(argv)

    today: _dt.date = _dt.date.today()
    if args.today:
        today = _dt.date.fromisoformat(args.today)
    if today < GATE_START_DATE:
        print(
            f"[A2] ERROR: --today ({today}) es anterior a GATE_START_DATE "
            f"({GATE_START_DATE}); nada que evaluar.",
            file=sys.stderr,
        )
        return 2

    days = _trading_days_calendar(GATE_START_DATE, today)
    pipeline_log = read_text(args.pipeline_log)
    updater_log = read_text(args.updater_log)
    state = load_state(args.state)
    evals = evaluate_window(days, pipeline_log, updater_log, state)
    record = make_record(evals)

    if not args.dry_run:
        write_record(record, args.output)
        print(f"[A2] OK -> {args.output}  ({len(days)} días hábiles, "
              f"streak={record['streak']}, n_clean={record['n_clean']})")
    else:
        print(f"[A2] DRY-RUN: {len(days)} días hábiles, "
              f"streak={record['streak']}, n_clean={record['n_clean']}")
    if args.print:
        _print_summary(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
