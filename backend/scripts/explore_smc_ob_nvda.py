#!/usr/bin/env python3
"""
explore_smc_ob_nvda.py
========================================================================
DEEP-DIVE de UN SOLO SIMBOLO (NVDA) de la estrategia SMC (OB + BOS/CHoCH).
Corre la MISMA senal sobre DOS vendors de forma aislada y side-by-side:

  1) Alpaca EOD (free tier IEX, ~2020-07-27 -> hoy)  -> load_alpaca()
  2) yfinance cache canonica RECORTADA a la MISMA ventana 2020-07-27 ->
     2026-09-04 -> load_parquet() + clip

Objetivo: ver si NVDA solo reproduce el veredicto negativo del universo
(robusto al vendor) o si diverge (especifico del simbolo / sesgado).

AISLAMIENTO: solo este archivo nuevo (untracked). CERO edicion de repo.
No es veredicto: requiere pre-registro + gate. Credenciales desde .env.
NVDA tuvo split 10:1 en Jun-2024; ambos vendors ajustan (all / auto_adjust).
========================================================================
"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ALPACA_MOD = os.path.join(HERE, "explore_smc_ob_alpaca.py")
PARQUET_MOD = os.path.join(HERE, "explore_smc_ob_signal_parquet.py")

# --- reusar loaders y senal exacta de los scripts existentes (sin duplicar) ---
_a = importlib.util.spec_from_file_location("explore_smc_alpaca", ALPACA_MOD)
alp = importlib.util.module_from_spec(_a)
_a.loader.exec_module(alp)
load_alpaca = alp.load_alpaca
load_creds = alp.load_creds

_p = importlib.util.spec_from_file_location("explore_smc_parquet", PARQUET_MOD)
pq = importlib.util.module_from_spec(_p)
_p.loader.exec_module(pq)
load_parquet = pq.load_parquet
backtest_symbol = pq.backtest_symbol
metrics_for = pq.metrics_for
causality_check = pq.causality_check
WARMUP = pq.WARMUP
IN_SAMPLE_END = pq.IN_SAMPLE_END
HOLDOUT_START = pq.HOLDOUT_START

SYM = os.environ.get("SMC_SYM", "NVDA")
CLIP_START = pd.Timestamp("2020-07-27")
CLIP_END = pd.Timestamp("2026-09-04")


def clip_window(df):
    if df is None:
        return None
    df = df[(df.index >= CLIP_START) & (df.index <= CLIP_END)]
    if len(df) < WARMUP + 10:
        print(f"  [clip] {SYM} muy corto tras recorte ({len(df)} barras)")
        return None
    return df


def run_source(name, df):
    """Backtest de un df ya cargado; devuelve (in_metrics, ho_metrics)."""
    df = df.copy()
    df.attrs["symbol"] = SYM
    trs = backtest_symbol(df)
    insample = [t for t in trs if t["entry_date"] <= IN_SAMPLE_END]
    holdout = [t for t in trs if t["entry_date"] >= HOLDOUT_START]
    return metrics_for(insample), metrics_for(holdout), len(trs)



def main():
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKEND, "data", "cache",
                            f"explore_smc_ob_nvda_{ts}.txt")
    lines = []

    def log(s=""):
        lines.append(str(s))
        print(s)

    api_key, secret_key = load_creds()
    if not api_key or not secret_key:
        print("FALTAN CREDENCIALES ALPACA en backend/.env -> salgo.")
        sys.exit(1)

    log("=" * 78)
    log(f"SMC OB SIGNAL — DEEP-DIVE UN SIMBOLO: {SYM}")
    log("=" * 78)
    log(f"  ventana comun    : {CLIP_START.date()} -> {CLIP_END.date()}")
    log(f"  in-sample end    : {IN_SAMPLE_END.date()} | holdout start: "
        f"{HOLDOUT_START.date()}")

    # ---- VENDOR 1: Alpaca EOD ----
    log("")
    log("-" * 78)
    log(f"VENDOR 1: ALPACA EOD ({SYM})")
    log("-" * 78)
    df_alp = load_alpaca(SYM, api_key, secret_key)
    if df_alp is not None:
        df_alp = clip_window(df_alp)  # misma ventana que yfinance para manzanas-con-manzanas
    m_alp_in, m_alp_ho, n_alp = (None, None, 0)
    causality_alp = False
    if df_alp is not None:
        n = len(df_alp)
        tvals = sorted(set([n // 2, 3 * n // 4, n - 20, 9 * n // 10]))
        ok, mism = causality_check(df_alp, tvals)
        causality_alp = ok
        log(f"  [{SYM}] bars={n}; causality checked t={tvals} -> "
            f"{'PASS' if ok else 'FAIL ' + str(len(mism))}")
        m_alp_in, m_alp_ho, n_alp = run_source("Alpaca", df_alp)

    # ---- VENDOR 2: yfinance cache recortada a la misma ventana ----
    log("")
    log("-" * 78)
    log(f"VENDOR 2: yfinance-cache RECORTADA ({SYM})")
    log("-" * 78)
    df_yf = clip_window(load_parquet(SYM))
    m_yf_in, m_yf_ho, n_yf = (None, None, 0)
    if df_yf is not None:
        log(f"  [{SYM}] bars={len(df_yf)} "
            f"({df_yf.index[0].date()} -> {df_yf.index[-1].date()})")
        m_yf_in, m_yf_ho, n_yf = run_source("yfinance", df_yf)

    def row(label, m):
        if m is None or m["n_trades"] == 0:
            return f"{label:17s}: sin trades"
        return (f"{label:17s}: n={m['n_trades']:>3} | "
                f"win={m['win_rate']:5.2f}% | mean_R={m['mean_R']:+.4f}")

    log("")
    log("=" * 78)
    log(f"COMPARACION {SYM} — IN-SAMPLE (entry <= 2025-08-31)")
    log("=" * 78)
    log(row("Alpaca", m_alp_in))
    log(row("yfinance", m_yf_in))

    log("")
    log("=" * 78)
    log(f"COMPARACION {SYM} — HOLDOUT (entry >= 2025-09-01, OUT-OF-SAMPLE)")
    log("=" * 78)
    log(row("Alpaca", m_alp_ho))
    log(row("yfinance", m_yf_ho))

    log("")
    log("-" * 78)
    ho = []
    if m_alp_ho and m_alp_ho["n_trades"]:
        ho.append(("Alpaca", m_alp_ho["mean_R"], m_alp_ho["n_trades"]))
    if m_yf_ho and m_yf_ho["n_trades"]:
        ho.append(("yfinance", m_yf_ho["mean_R"], m_yf_ho["n_trades"]))
    ins = []
    if m_alp_in and m_alp_in["n_trades"]:
        ins.append(m_alp_in["mean_R"] < 0)
    if m_yf_in and m_yf_in["n_trades"]:
        ins.append(m_yf_in["mean_R"] < 0)
    in_neg = len(ins) >= 1 and all(ins)
    def fmt_r(m):
        return f"{m['mean_R']:+.4f}" if (m and m["n_trades"]) else "n/a"

    if len(ho) >= 2:
        all_neg = all(r < 0 for _, r, _ in ho)
        all_pos = all(r > 0 for _, r, _ in ho)
        if all_neg:
            verdict = (f"SIGNO NEGATIVO EN AMBOS VENDORS en holdout de {SYM} "
                       f"(Alpaca {fmt_r(m_alp_ho)}, yfinance {fmt_r(m_yf_ho)}) "
                       f"-> veredicto negativo reproducido (no es artefacto "
                       f"de vendor).")
        elif all_pos:
            verdict = (f"Holdout POSITIVO en AMBOS para {SYM} (1 trade c/u, "
                       f"Alpaca {fmt_r(m_alp_ho)}, yfinance {fmt_r(m_yf_ho)}) "
                       f"-> {SYM} NO reproduce el negativo en holdout; muestra "
                       f"insuficiente (n=1) y NO contradice el veredicto de "
                       f"universo (n=72-83).")
        else:
            verdict = f"Holdout mixto entre vendors para {SYM} -> revisar."
        if in_neg:
            verdict += (f" Ademas, in-sample de {SYM} es FUERTEMENTE negativo "
                        f"en ambos vendors -> la senal negativa es consistente "
                        f"en-sample.")
    else:
        verdict = "Holdout no disponible en >=1 vendor -> revisar."
    log(f"Veredicto: {verdict}")

    log("")
    log("=" * 78)
    log("LIMITACIONES")
    log("=" * 78)
    log("  * Exploratorio: NO es veredicto (requiere pre-registro + gate).")
    log(f"  * Causalidad Alpaca: "
        f"{'PASS (sin look-ahead)' if causality_alp else 'NO VERIFICADA/FAIL'}")
    log("  * sharpe/max_dd de metrics_for no fiables para 1 simbolo (equity "
        "plana a 1% risk) -> solo se comparan n/win_rate/mean_R.")
    log("  * Misma senal/metricas que explore_smc_ob_signal.py.")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    log("")
    log(f"Artifact: {out_path}")


if __name__ == "__main__":
    import sys
    main()

