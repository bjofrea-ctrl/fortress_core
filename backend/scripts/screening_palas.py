"""Screening "vendedor de palas" (A6.3) — separacion habilitadores IA vs resto.

Pre-registro: PRE_REGISTRO_SCREENING_PALAS.md (aprobado por Boris 2026-08-27).
Correr UNA sola vez desde backend/:
    .venv/bin/python -m scripts.screening_palas

3 instancias frescas de BacktestEngine, una por subconjunto (PALA/RESTO/POOLED).
price_data filtrado al subconjunto; market_data intacto (MACRO) en las 3.
Todo lo demas congelado (score, gates, costos, stops, execution_lag).

Output: data/cache/screening_palas_<YYYYMMDD_HHMMSS>.txt + .json
"""
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


CHECKPOINT_PATH = "data/cache/screening_palas_checkpoint.json"


def _load_checkpoint():
    """Robustez de ejecucion, NO metodologia: si el proceso muere a mitad
    (crash de la sesion que lo lanzo, disco lleno, corte de energia, etc.)
    no se pierde el computo ya hecho. No cambia que se corre, ni los
    umbrales, ni el criterio -- solo evita repetir trabajo ya terminado."""
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_checkpoint(table):
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as fh:
        json.dump(table, fh, ensure_ascii=False, indent=2)


def main():
    ts = dt.now().strftime("%Y%m%d_%H%M%S")
    out_txt = f"data/cache/screening_palas_{ts}.txt"
    out_json = f"data/cache/screening_palas_{ts}.json"

    table = _load_checkpoint()
    if table:
        done = sum(len(v) for v in table.values())
        print(f"[screening_palas] checkpoint encontrado: {done}/9 corridas ya completadas, retomando...")

    print(f"[screening_palas] cargando universo {len(SYMBOLS)} simbolos + MACRO...")
    full_price = load_universe(SYMBOLS, "2016-01-01", "2026-08-14")
    market_data = load_universe(MACRO, "2016-01-01", "2026-08-14")

    resto = [s for s in SYMBOLS if s not in PALA]
    subsets = {
        "PALA": {s: full_price[s] for s in PALA if s in full_price},
        "RESTO": {s: full_price[s] for s in resto if s in full_price},
        "POOLED": dict(full_price),
    }

    for subset_name, subset_price in subsets.items():
        table.setdefault(subset_name, {})
        for wname, start, end in WINDOWS:
            if wname in table[subset_name]:
                print(f"[screening_palas] {subset_name} {wname} ya en checkpoint, salteando.")
                continue
            print(f"[screening_palas] {subset_name} {wname} ({start} -> {end})...")
            sharpe, dsr, n_trades = run_subset(
                subset_price, market_data, start, end
            )
            table[subset_name][wname] = {
                "sharpe": round(sharpe, 4),
                "dsr": round(dsr, 4),
                "n_trades": n_trades,
            }
            _save_checkpoint(table)

    # --- tabla comparativa ---
    lines = []
    lines.append("SCREENING VENDEDOR DE PALAS (A6.3) — resultado")
    lines.append(f"ts={ts}  PALA={PALA}  N_PALA={len(PALA)}  N_RESTO={len(resto)}")
    lines.append("")
    header = f"{'':8} {'W1':>22} {'W2':>22} {'W3':>22}"
    lines.append(header)
    for subset_name in ("PALA", "RESTO", "POOLED"):
        row = f"{subset_name:8}"
        for wname, _, _ in WINDOWS:
            c = table[subset_name][wname]
            row += f"  S={c['sharpe']:>7.4f} D={c['dsr']:.4f} n={c['n_trades']:>3}"
        lines.append(row)

    # --- criterio primario: PALA > RESTO en Sharpe Y DSR en >=2/3 ventanas ---
    lines.append("")
    lines.append("--- Criterio primario (PALA > RESTO en Sharpe Y DSR, >=2/3 ventanas) ---")
    wins = 0
    evaluables = 0
    for wname, _, _ in WINDOWS:
        p = table["PALA"][wname]
        r = table["RESTO"][wname]
        sup_sharpe = p["sharpe"] > r["sharpe"]
        sup_dsr = p["dsr"] > r["dsr"]
        is_evaluable = p["n_trades"] >= 30
        if is_evaluable:
            evaluables += 1
        if is_evaluable and sup_sharpe and sup_dsr:
            wins += 1
            lines.append(f"  {wname}: PALA gana (S {p['sharpe']:.4f}>{r['sharpe']:.4f}, D {p['dsr']:.4f}>{r['dsr']:.4f}, n={p['n_trades']})")
        else:
            razon = []
            if not is_evaluable:
                razon.append(f"n={p['n_trades']}<30")
            if not sup_sharpe:
                razon.append(f"S_PALA={p['sharpe']:.4f}<=S_RESTO={r['sharpe']:.4f}")
            if not sup_dsr:
                razon.append(f"D_PALA={p['dsr']:.4f}<=D_RESTO={r['dsr']:.4f}")
            lines.append(f"  {wname}: PALA NO gana ({', '.join(razon)})")

    if evaluables == 0:
        required_wins = 3
    elif evaluables == 1:
        required_wins = 1
    else:
        required_wins = 2

    dsr_en_victorias = all(
        table["PALA"][wname]["dsr"] > 0.50
        for wname, _, _ in WINDOWS
        if table["PALA"][wname]["n_trades"] >= 30
        and table["PALA"][wname]["sharpe"] > table["RESTO"][wname]["sharpe"]
        and table["PALA"][wname]["dsr"] > table["RESTO"][wname]["dsr"]
    )

    primary_pass = (wins >= required_wins) and dsr_en_victorias
    lines.append(f"  ventanas_evaluables={evaluables}  victorias_PALA={wins}  requerido={required_wins}")
    lines.append(f"  DSR_PALA>0.50 en victorias={dsr_en_victorias}")

    # --- check sanidad POOLED vs baseline ---
    lines.append("")
    lines.append("--- Check sanidad POOLED vs baseline_clean ---")
    pooled_ok_windows = 0
    for wname, _, _ in WINDOWS:
        p = table["POOLED"][wname]
        b = BASELINE[wname]
        d_dsr = abs(p["dsr"] - b["dsr"])
        d_sharpe = abs(p["sharpe"] - b["sharpe"])
        ok = (d_dsr <= TOL_DSR) and (d_sharpe <= TOL_SHARPE)
        if ok:
            pooled_ok_windows += 1
        lines.append(
            f"  {wname}: POOLED S={p['sharpe']:.4f} D={p['dsr']:.4f} | "
            f"baseline S={b['sharpe']:.4f} D={b['dsr']:.4f} | "
            f"dS={d_sharpe:.4f}(tol {TOL_SHARPE}) dD={d_dsr:.4f}(tol {TOL_DSR}) "
            f"{'OK' if ok else 'FUERA'}"
        )
    sanity_ok = pooled_ok_windows >= 2
    lines.append(f"  ventanas_dentro_tolerancia={pooled_ok_windows}/3  -> {'OK' if sanity_ok else 'FUERA -> NO_INTERPRETABLE'}")

    # --- veredicto mecanico ---
    lines.append("")
    if not sanity_ok:
        veredicto = "NO_CUMPLE"
        nota = "NO_INTERPRETABLE: POOLED fuera de tolerancia vs baseline en >=2 ventanas (posible bug de implementacion)"
    elif primary_pass:
        veredicto = "NO_CUMPLE" if not dsr_en_victorias else "CUMPLE"
        nota = "CUMPLE criterio primario (PALA>RESTO en Sharpe Y DSR en >=2/3 ventanas, DSR>0.50, >=30 trades)"
    else:
        veredicto = "NO_CUMPLE"
        if wins >= required_wins and not dsr_en_victorias:
            nota = "ZONA GRIS: PALA supera en Sharpe Y DSR pero DSR<=0.50 en ventanas victoriosas -> NO_CUMPLE binario"
        else:
            nota = f"PALA NO supera RESTO en >=2/3 ventanas (victorias={wins}, requerido={required_wins})"

    lines.append(f"VEREDICTO: {veredicto}")
    lines.append(f"Nota: {nota}")

    report = "\n".join(lines)
    print("\n" + report)

    with open(out_txt, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")

    payload = {
        "ts": ts,
        "PALA": PALA,
        "N_PALA": len(PALA),
        "N_RESTO": len(resto),
        "table": table,
        "criterio_primario": {
            "victorias": wins,
            "requerido": required_wins,
            "evaluables": evaluables,
            "dsr_en_victorias": dsr_en_victorias,
            "pass": primary_pass,
        },
        "check_sanidad": {
            "ventanas_ok": pooled_ok_windows,
            "pass": sanity_ok,
        },
        "veredicto": veredicto,
        "nota": nota,
    }
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(f"\nArtefactos: {out_txt}  {out_json}")
    return veredicto, out_txt


if __name__ == "__main__":
    main()
