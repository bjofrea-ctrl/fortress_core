#!/usr/bin/env python3
"""
explore_smc_ob_signal_parquet.py
========================================================================
RE-RUN de explore_smc_ob_signal.py pero con la PRICE CACHE CANONICA del repo
(real) en lugar de un yfinance fresco.

POR QUE: el worktree de la tarea no tenia parquets (0 archivos), asi que la
corrida original cayo a un yfinance.download FRESCO. La fuente de precios
vetada y protegida por cache_integrity del proyecto vive en el repo canonico:
  /Users/boris/Desktop/fortress_core/backend/data/cache/*.parquet
(170 archivos; 50/50 simbolos presentes; rango 2009 -> 2026-09-04;
 columnas open/high/low/close/volume).

Cargamos ESOS parquets en modo READ-ONLY (sin copiar ni editar) para que el
backtest corra sobre EXACTAMENTE los mismos datos que consumen todos los demas
trials de Fortress -> responde directo a "estamos evaluando bien?".

TODO lo demas (senal pre-stated, check de causalidad, split in-sample/holdout,
metricas) es IDENTICO a explore_smc_ob_signal.py -> comparacion manzanas con
manzanas contra la corrida con yfinance.
========================================================================
"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ORIGINAL = os.path.join(HERE, "explore_smc_ob_signal.py")
# READ-ONLY canonical cache (repo real, no se toca)
CANON_DIR = "/Users/boris/Desktop/fortress_core/backend/data/cache"

# Reusar EXACTAMENTE la logica del original (senal, backtest, metrics, causality)
_spec = importlib.util.spec_from_file_location("explore_smc_orig", ORIGINAL)
_orig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_orig)
backtest_symbol = _orig.backtest_symbol
metrics_for = _orig.metrics_for
causality_check = _orig.causality_check
SYMBOLS = _orig.SYMBOLS
WARMUP = _orig.WARMUP
IN_SAMPLE_END = _orig.IN_SAMPLE_END
HOLDOUT_START = _orig.HOLDOUT_START


def load_parquet(sym: str):
    p = os.path.join(CANON_DIR, f"{sym}.parquet")
    if not os.path.exists(p):
        print(f"  [load] {sym} missing parquet")
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        print(f"  [load] {sym} parquet read failed: {type(e).__name__}: {e}")
        return None
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    # Canonical cache has BOTH lowercase (modern adjusted OHLC) and legacy
    # capitalized columns -> dedupe keeping the first (lowercase) occurrence,
    # exactly as the rest of the repo's price consumers expect.
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    keep = ["open", "high", "low", "close"]
    if not all(k in df.columns for k in keep):
        print(f"  [load] {sym} missing cols")
        return None
    df = df[keep].copy()
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=keep)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if len(df) < WARMUP + 10:
        print(f"  [load] {sym} too short ({len(df)} bars)")
        return None
    return df


def main():
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKEND, "data", "cache",
                            f"explore_smc_ob_parquet_{ts}.txt")
    lines = []

    def log(s=""):
        lines.append(str(s))
        print(s)

    log("=" * 78)
    log("SMC OB SIGNAL — RE-RUN SOBRE CACHE PARQUET CANONICA (read-only)")
    log(f"  source: {CANON_DIR}  (vetada, protegida por cache_integrity)")
    log("=" * 78)

    latest = {}
    for s in SYMBOLS:
        d = load_parquet(s)
        if d is not None:
            latest[s] = d.index[-1].date()
    log(f"  simbolos con parquet: {len(latest)} / {len(SYMBOLS)}")
    if latest:
        ld = list(latest.values())
        log(f"  fin de rango de datos: min={min(ld)} max={max(ld)}")
    log("")

    log("-" * 78)
    log("CAUSALITY CHECK (market_structure_history, AAPL)")
    log("-" * 78)
    causality_ok = False
    aapl = load_parquet("AAPL")
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
    log("BACKTEST (50 simbolos, parquet canonica)")
    log("-" * 78)
    all_trades = []
    failed = []
    for i, sym in enumerate(SYMBOLS, 1):
        df = load_parquet(sym)
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
    log(f"  sharpe_eq  : {m_in['sharpe_eq']:.3f}  (daily equity, ann sqrt(252), 1% risk/trade)")
    log(f"  max_dd_pct : {m_in['max_dd_pct']:.2f}%")

    log("")
    log("=" * 78)
    log("METRICAS - HOLDOUT (entry >= 2025-09-01, SEALED OUT-OF-SAMPLE)")
    log("=" * 78)
    m_ho = metrics_for(holdout)
    log(f"  n_trades   : {m_ho['n_trades']}")
    log(f"  win_rate   : {m_ho['win_rate']:.2f}%")
    log(f"  mean_R     : {m_ho['mean_R']:.4f}")
    log(f"  sharpe_eq  : {m_ho['sharpe_eq']:.3f}  (daily equity, ann sqrt(252), 1% risk/trade)")
    log(f"  max_dd_pct : {m_ho['max_dd_pct']:.2f}%")

    log("")
    log("=" * 78)
    log("LIMITACIONES")
    log("=" * 78)
    log("  * Exploratorio: NO es veredicto. Requeriria pre-registro + gate")
    log("    (PBO<0.10, DSR>=0.95, Bonferroni/CSCV, holdout sellado 2025-09-01).")
    log(f"  * Causalidad (market_structure_history): "
        f"{'PASS (sin look-ahead)' if causality_ok else 'NO VERIFICADA / FAIL'}")
    log("  * DATA: parquet cache canonica del repo real (READ-ONLY, sin yfinance fresco).")
    log("  * Misma senal/metricas que explore_smc_ob_signal.py -> comparacion directa.")
    log(f"  * Warmup={WARMUP}b. Simbolos fallidos: {failed if failed else 'ninguno'}.")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    log("")
    log(f"Artifact: {out_path}")


if __name__ == "__main__":
    main()

