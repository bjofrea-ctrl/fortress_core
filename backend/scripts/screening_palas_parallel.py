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
# Baseline vigente (costo 0.10%/lado) para el check CORREGIDO §4.2.
# Valores extraidos de backend/data/cache/baseline_clean_20260828_183624.txt
# que ya trae DSR calculado con N_TRIALS=17 (propio de su familia universe50).
# Se usa SOLO para la comparacion del check de sanidad, no como default del screening.
BASELINE_VIGENTE_N17 = {
    "W1": {"dsr": 0.1508, "sharpe": 0.5586},
    "W2": {"dsr": 0.0900, "sharpe": 0.3478},
    "W3": {"dsr": 0.0932, "sharpe": 0.3085},
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


def run_subset_with_dsr17(price_data, market_data, start, end):
    """Corre el subset y devuelve DSR con N_TRIALS=5 (real) y DSR_17 (solo check).

    DISTINCION CRITICA (PRE_REGISTRO_SANEAMIENTO_CHECK_A63.md §2-§4):
    - El DSR "real" de PALA/RESTO/POOLED (tabla, criterio primario) sigue en
      n_trials=5, que es el default de la familia signal_diagnosis (gate laxo
      escalon 1, deliberadamente permisivo para un screening barato).
    - El DSR_17 es una IGUALACION AD-HOC SOLO para la comparacion del check
      de sanidad §4.2 (POOLED vs baseline vigente). El baseline usa N_TRIALS=17
      por herencia de backtest_universe50 (familia universe50, validacion de la
      estrategia principal) — no es doctrina global. Para que la comparacion sea
      valida, ambos lados deben usar el mismo N_TRIALS; por eso se recalcula
      DSR_17 aqui, sin cambiar el default del motor ni de la tabla.
    """
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
    m5 = res["metrics"]  # default n_trials=5
    # Calculo ad-hoc con N_TRIALS=17 solo para el check (no se guarda en tabla)
    m17 = engine.calculate_metrics(res["equity_curve"], res["trades"], n_trials=17)
    return m5["sharpe_ratio"], m5["deflated_sharpe"], m17["deflated_sharpe"], m5["total_trades"]


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

    # Para POOLED guardamos tambien dsr17 (N_TRIALS=17) solo para el check corregido.
    # La tabla "real" (criterio primario) sigue en n_trials=5.
    for wname, start, end in WINDOWS:
        if wname in table and subset != "POOLED":
            print(f"[screening_palas_parallel:{subset}] {wname} ya en checkpoint, salteando.")
            continue
        if subset == "POOLED" and wname in table and "dsr17" in table[wname]:
            print(f"[screening_palas_parallel:{subset}] {wname} ya en checkpoint (con dsr17), salteando.")
            continue
        if subset == "POOLED" and wname in table and "dsr17" not in table[wname]:
            # checkpoint viejo sin dsr17: recalcular solo el DSR_17 ad-hoc
            print(f"[screening_palas_parallel:{subset}] {wname} en checkpoint sin dsr17 — recalculando DSR_17 ad-hoc...")
            # Re-ejecutar ventana para obtener equity_curve/trades y recalcular con N=17
            _, _, dsr17, _ = run_subset_with_dsr17(subset_price, market_data, start, end)
            table[wname]["dsr17"] = round(dsr17, 4)
            _save_checkpoint(subset, table)
            print(f"[screening_palas_parallel:{subset}] {wname} -> dsr17={dsr17:.4f} (agregado a checkpoint)")
            continue
        print(f"[screening_palas_parallel:{subset}] {wname} ({start} -> {end})...")
        if subset == "POOLED":
            sharpe, dsr5, dsr17, n_trades = run_subset_with_dsr17(subset_price, market_data, start, end)
            table[wname] = {"sharpe": round(sharpe, 4), "dsr": round(dsr5, 4), "dsr17": round(dsr17, 4), "n_trades": n_trades}
            _save_checkpoint(subset, table)
            print(f"[screening_palas_parallel:{subset}] {wname} -> S={sharpe:.4f} D5={dsr5:.4f} D17={dsr17:.4f} n={n_trades} (checkpoint guardado)")
        else:
            sharpe, dsr, n_trades = run_subset(subset_price, market_data, start, end)
            table[wname] = {"sharpe": round(sharpe, 4), "dsr": round(dsr, 4), "n_trades": n_trades}
            _save_checkpoint(subset, table)
            print(f"[screening_palas_parallel:{subset}] {wname} -> S={sharpe:.4f} D={dsr:.4f} n={n_trades} (checkpoint guardado)")

    lines = []
    lines.append(f"SCREENING VENDEDOR DE PALAS (A6.3) — {subset} — ts={ts}")
    lines.append(f"PALA={PALA}  N_PALA={len(PALA)}  N_RESTO={len(resto)}")
    for wname, _, _ in WINDOWS:
        c = table[wname]
        # Mostrar dsr17 si existe (POOLED) para trazabilidad
        if "dsr17" in c:
            lines.append(f"  {wname}: S={c['sharpe']:.4f} D={c['dsr']:.4f} (D17={c['dsr17']:.4f}) n={c['n_trades']}")
        else:
            lines.append(f"  {wname}: S={c['sharpe']:.4f} D={c['dsr']:.4f} n={c['n_trades']}")

    # --- Check de sanidad §4.2 CORREGIDO (solo para POOLED) ---
    if subset == "POOLED":
        lines.append("")
        lines.append("--- Check sanidad §4.2 CORREGIDO (POOLED vs baseline_clean_20260828_183624.txt, ambos N_TRIALS=17 ad-hoc) ---")
        lines.append("Nota: DSR_17 es igualacion ad-hoc SOLO para esta comparacion. El DSR real de la tabla sigue en n_trials=5 (familia signal_diagnosis).")
        corregido_ok = 0
        for wname, _, _ in WINDOWS:
            c = table[wname]
            b = BASELINE_VIGENTE_N17[wname]
            # Usar dsr17 para la comparacion corregida
            pooled_dsr17 = c.get("dsr17", c["dsr"])
            d_sharpe = abs(c["sharpe"] - b["sharpe"])
            d_dsr = abs(pooled_dsr17 - b["dsr"])
            ok = (d_sharpe <= TOL_SHARPE) and (d_dsr <= TOL_DSR)
            if wname == "W3":
                # W3 queda sin resolver aunque el gate 2/3 se cumpla — no se cuenta como pasada
                lines.append(f"  {wname}: POOLED S={c['sharpe']:.4f} D17={pooled_dsr17:.4f} | baseline S={b['sharpe']:.4f} D17={b['dsr']:.4f} | dS={d_sharpe:.4f} dD={d_dsr:.4f} -> FUERA (sin resolver, requiere investigacion aparte)")
                # No sumar a corregido_ok aunque ok fuese True — W3 no se cuenta
            else:
                if ok:
                    corregido_ok += 1
                lines.append(f"  {wname}: POOLED S={c['sharpe']:.4f} D17={pooled_dsr17:.4f} | baseline S={b['sharpe']:.4f} D17={b['dsr']:.4f} | dS={d_sharpe:.4f}(tol {TOL_SHARPE}) dD={d_dsr:.4f}(tol {TOL_DSR}) -> {'OK' if ok else 'FUERA'}")
        lines.append(f"  ventanas_ok_corregido (sin contar W3)={corregido_ok}/2 -> {'OK (2/2)' if corregido_ok==2 else 'FUERA'} -> gate 2/3 con W3 sin resolver")
        lines.append("  W3: sin resolver, requiere investigacion aparte (no se cuenta como ventana que paso, aunque el criterio 2/3 alcance para el gate)")

    report = "\n".join(lines)
    print("\n" + report)
    with open(out_txt, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    payload = {"ts": ts, "subset": subset, "PALA": PALA, "table": table}
    if subset == "POOLED":
        payload["baseline_vigente_n17"] = BASELINE_VIGENTE_N17
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\nArtefactos: {out_txt}  {out_json}")
    print(f"Checkpoint: {checkpoint_path(subset)}")


if __name__ == "__main__":
    main()
