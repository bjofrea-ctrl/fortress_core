"""Screening "vendedor de palas" (A6.3) — modo paralelo por subconjunto.

Variante de screening_palas.py que corre UN solo subconjunto (PALA/RESTO/POOLED).
Mantiene checkpoint por ventana, pero aislado por subconjunto para evitar race:

  checkpoint: data/cache/screening_palas_checkpoint_{SUBSET}.json
  artefacto:  data/cache/screening_palas_{SUBSET}_{YYYYMMDD_HHMMSS}.txt/.json
  log nohup:  data/cache/screening_palas_{SUBSET}_{ts}.nohup.log  (lo pone el launcher)

Uso (desde backend/, con el venv correcto):

  .venv/bin/python -m scripts.screening_palas_parallel --subset PALA
  .venv/bin/python -m scripts.screening_palas_parallel --subset RESTO
  .venv/bin/python -m scripts.screening_palas_parallel --subset POOLED

Cada corrida debe lanzarse como proceso independiente de verdad:

  nohup .venv/bin/python -u -m scripts.screening_palas_parallel --subset PALA \
    > data/cache/screening_palas_PALA_$(date +%Y%m%d_%H%M%S).nohup.log 2>&1 & disown

PPID debe ser 1 tras cerrar la shell que lo lanzó (hereda init/launchd). Verificar con:

  ps -o pid,ppid,command | grep screening_palas_parallel

Matematicamente identico a screening_palas.py: mismo universo, ventanas,
costos, execution_lag, BASELINE/TOL. Solo cambia el aislamiento de archivos.
NO toca N_TRIALS, rangos de fecha, tolerancias ni pre-registro.
"""
import argparse
import json
import os
import sys
from datetime import datetime as dt

import pandas as pd

from app.api.routes.opportunities_universe import SYMBOLS
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe

PALA = ["NVDA", "AVGO", "QCOM", "MSFT", "ORCL", "CSCO"]
MACRO = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
WINDOWS = [
    ("W1", "2020-01-01", "2021-12-31"),
    ("W2", "2022-01-01", "2023-12-31"),
    ("W3", "2024-01-01", "2026-08-04"),
]
BASELINE = {
    "W1": {"dsr": 0.0714, "sharpe": 0.2562},
    "W2": {"dsr": 0.0284, "sharpe": -0.0542},
    "W3": {"dsr": 0.1727, "sharpe": 0.5299},
}
TOL_DSR = 0.05
TOL_SHARPE = 0.15

ALLOWED = {"PALA", "RESTO", "POOLED"}


def run_subset(price_data, market_data, start, end):
    engine = BacktestEngine(initial_capital=25000)
    res = engine.run(
        price_data,
        market_data,
        pd.Timestamp(start),
        pd.Timestamp(end),
        commission=0.0005,
        slippage=0.0005,
        execution_lag_days=1,
    )
    m = res["metrics"]
    return m["sharpe_ratio"], m["deflated_sharpe"], m["total_trades"]


def checkpoint_path(subset: str) -> str:
    return f"data/cache/screening_palas_checkpoint_{subset}.json"


def _load_checkpoint(subset: str):
    path = checkpoint_path(subset)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_checkpoint(subset: str, table: dict):
    path = checkpoint_path(subset)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(table, fh, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="screening_palas por subconjunto (paralelo)")
    parser.add_argument("--subset", required=True, choices=sorted(ALLOWED), help="PALA | RESTO | POOLED")
    args = parser.parse_args()
    subset = args.subset

    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    out_txt = f"data/cache/screening_palas_{subset}_{ts}.txt"
    out_json = f"data/cache/screening_palas_{subset}_{ts}.json"

    table = _load_checkpoint(subset)
    if table:
        done = len(table)
        print(f"[screening_palas_parallel:{subset}] checkpoint encontrado: {done}/3 ventanas ya completadas, retomando... ({checkpoint_path(subset)})")
    else:
        print(f"[screening_palas_parallel:{subset}] sin checkpoint previo, arrancando limpio ({checkpoint_path(subset)})")

    print(f"[screening_palas_parallel:{subset}] cargando universo {len(SYMBOLS)} simbolos + MACRO...")
    full_price = load_universe(SYMBOLS, "2016-01-01", "2026-08-14")
    market_data = load_universe(MACRO, "2016-01-01", "2026-08-14")

    resto = [s for s in SYMBOLS if s not in PALA]
    subsets = {
        "PALA": {s: full_price[s] for s in PALA if s in full_price},
        "RESTO": {s: full_price[s] for s in resto if s in full_price},
        "POOLED": dict(full_price),
    }
    if subset not in subsets:
        print(f"subset {subset} no encontrado", file=sys.stderr)
        sys.exit(2)
    subset_price = subsets[subset]
    print(f"[screening_palas_parallel:{subset}] N={len(subset_price)}  ts={ts}")

    for wname, start, end in WINDOWS:
        if wname in table:
            print(f"[screening_palas_parallel:{subset}] {wname} ya en checkpoint, salteando.")
            continue
        print(f"[screening_palas_parallel:{subset}] {wname} ({start} -> {end})...")
        sharpe, dsr, n_trades = run_subset(subset_price, market_data, start, end)
        table[wname] = {"sharpe": round(sharpe, 4), "dsr": round(dsr, 4), "n_trades": n_trades}
        _save_checkpoint(subset, table)
        print(f"[screening_palas_parallel:{subset}] {wname} -> S={sharpe:.4f} D={dsr:.4f} n={n_trades} (checkpoint guardado)")

    lines = []
    lines.append(f"SCREENING VENDEDOR DE PALAS (A6.3) — {subset} — ts={ts}")
    lines.append(f"PALA={PALA}  N_PALA={len(PALA)}  N_RESTO={len(resto)}")
    for wname, _, _ in WINDOWS:
        c = table[wname]
        lines.append(f"  {wname}: S={c['sharpe']:.4f} D={c['dsr']:.4f} n={c['n_trades']}")
    report = "\n".join(lines)
    print("\n" + report)
    with open(out_txt, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    payload = {"ts": ts, "subset": subset, "PALA": PALA, "table": table}
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\nArtefactos: {out_txt}  {out_json}")
    print(f"Checkpoint: {checkpoint_path(subset)}")


if __name__ == "__main__":
    main()
