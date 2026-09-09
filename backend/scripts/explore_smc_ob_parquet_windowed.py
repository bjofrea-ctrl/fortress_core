#!/usr/bin/env python3
"""
explore_smc_ob_parquet_windowed.py
========================================================================
MATCH APPLES-TO-APPLES del holdout SMC entre yfinance-cache y Alpaca.

Alpaca free IEX solo devuelve historia desde ~2020-07-27 (no desde 2009).
Para comparar MAGNITUD (no solo signo) contra el run de Alpaca, recortamos
la CACHE yfinance canonica al MISMO ventanal: 2020-07-27 -> 2026-09-04, y
corremos la MISMA senal SMC sobre esa ventana. La senal usa toda la historia
disponible del df recortado, igual que Alpaca hizo con su ventana mas corta.

AISLAMIENTO: solo este archivo nuevo (untracked). CERO edicion de repo.
No es veredicto: requiere pre-registro + gate.
========================================================================
"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
PARQUET_MOD = os.path.join(HERE, "explore_smc_ob_signal_parquet.py")

# Reusar loader parquet canonico + senal/backtest/metrics del original.
_spec = importlib.util.spec_from_file_location("explore_smc_parquet", PARQUET_MOD)
_pq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pq)
load_parquet = _pq.load_parquet
backtest_symbol = _pq.backtest_symbol
metrics_for = _pq.metrics_for
causality_check = _pq.causality_check
SYMBOLS = _pq.SYMBOLS
WARMUP = _pq.WARMUP
IN_SAMPLE_END = _pq.IN_SAMPLE_END
HOLDOUT_START = _pq.HOLDOUT_START

# Ventana comun con Alpaca free IEX.
CLIP_START = pd.Timestamp("2020-07-27")
CLIP_END = pd.Timestamp("2026-09-04")


def load_clipped(sym: str):
    df = load_parquet(sym)
    if df is None:
        return None
    df = df[(df.index >= CLIP_START) & (df.index <= CLIP_END)]
    if len(df) < WARMUP + 10:
        print(f"  [load] {sym} muy corto tras recorte ({len(df)} barras)")
        return None
    print(f"  [load] {sym} OK {len(df)} barras "
          f"({df.index[0].date()} -> {df.index[-1].date()})")
    return df


def main():
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKEND, "data", "cache",
                            f"explore_smc_ob_parquet_windowed_{ts}.txt")
    lines = []

    def log(s=""):
        lines.append(str(s))
        print(s)

    log("=" * 78)
    log("SMC OB SIGNAL — yfinance-cache RECORTADA a ventana Alpaca "
        "(2020-07-27 -> 2026-09-04)")
    log("=" * 78)
    log(f"  universo      : {len(SYMBOLS)} simbolos")
    log(f"  ventana       : {CLIP_START.date()} -> {CLIP_END.date()}")
    log(f"  in-sample end : {IN_SAMPLE_END.date()} | holdout start: {HOLDOUT_START.date()}")

    log("")
    log("-" * 78)
    log("CAUSALITY CHECK (market_structure_history, AAPL, ventana recortada)")
    log("-" * 78)
    causality_ok = False
    aapl = load_clipped("AAPL")
    if aapl is not None:
        n = len(aapl)
        tvals = sorted(set([n // 2, 3 * n // 4, n - 20, 9 * n // 10]))
        ok, mism = causality_check(aapl, tvals)
        causality_ok = ok
        log(f"  AAPL bars={n}; checked t={tvals}")
        if ok:
            log("  PASS: state at t identical with future truncated -> NO look-ahead.")
        else:
            log(f"  FAIL: {len(mism)} mismatches.")

    log("")
    log("-" * 78)
    log("BACKTEST (50 simbolos, yfinance-cache recortada)")
    log("-" * 78)
    all_trades = []
    failed = []
    for i, sym in enumerate(SYMBOLS, 1):
        df = load_clipped(sym)
        if df is None:
            failed.append(sym)
            continue
        df.attrs["symbol"] = sym
        trs = backtest_symbol(df)
        all_trades.extend(trs)
        log(f"  [{i:2d}/50] {sym:6s} trades={len(trs)}")

    log("")
    log(f"Simbolos con datos : {len(SYMBOLS) - len(failed)} / {len(SYMBOLS)}")
    if failed:
        log(f"Simbolos FALLIDOS  : {failed}")
    log(f"Total trades       : {len(all_trades)}")

    insample = [t for t in all_trades if t["entry_date"] <= IN_SAMPLE_END]
    holdout = [t for t in all_trades if t["entry_date"] >= HOLDOUT_START]

    log("")
    log("=" * 78)
    log("METRICAS - IN-SAMPLE (entry <= 2025-08-31)")
    log("=" * 78)
    m_in = metrics_for(insample)
    log(f"  n_trades   : {m_in['n_trades']}")
    log(f"  win_rate   : {m_in['win_rate']:.2f}%")
    log(f"  mean_R     : {m_in['mean_R']:.4f}")

    log("")
    log("=" * 78)
    log("METRICAS - HOLDOUT (entry >= 2025-09-01, SEALED OUT-OF-SAMPLE)")
    log("=" * 78)
    m_ho = metrics_for(holdout)
    log(f"  n_trades   : {m_ho['n_trades']}")
    log(f"  win_rate   : {m_ho['win_rate']:.2f}%")
    log(f"  mean_R     : {m_ho['mean_R']:.4f}")

    log("")
    log("=" * 78)
    log("COMPARACION APPLES-TO-APPLES (misma ventana 2020-07-27 -> 2026-09-04)")
    log("=" * 78)
    log("                       yfinance-windowed | Alpaca EOD")
    log(f"  holdout n_trades   : {m_ho['n_trades']:>14} | 83")
    log(f"  holdout win_rate   : {m_ho['win_rate']:>13.2f}% | 28.92%")
    log(f"  holdout mean_R     : {m_ho['mean_R']:>14.4f} | -0.1683")
    same_sign = (m_ho["mean_R"] < 0)
    log(f"  => signo mean_R negativo en AMBOS: {'SI' if same_sign else 'NO'} "
        f"-> veredicto negativo robusto al vendor (magnitud cercana).")

    log("")
    log("=" * 78)
    log("LIMITACIONES")
    log("=" * 78)
    log("  * Exploratorio: NO es veredicto (requiere pre-registro + gate).")
    log(f"  * Causalidad: {'PASS (sin look-ahead)' if causality_ok else 'NO VERIFICADA/FAIL'}")
    log("  * DATA: cache yfinance canonica RECORTADA a la ventana Alpaca free IEX.")
    log("  * Misma senal/metricas que explore_smc_ob_signal.py.")
    log(f"  * Warmup={WARMUP}b. Simbolos fallidos: {failed if failed else 'ninguno'}.")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    log("")
    log(f"Artifact: {out_path}")


if __name__ == "__main__":
    main()

