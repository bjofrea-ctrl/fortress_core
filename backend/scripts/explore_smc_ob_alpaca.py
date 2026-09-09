#!/usr/bin/env python3
"""
explore_smc_ob_alpaca.py
========================================================================
RE-RUN de explore_smc_ob_signal.py pero con DATA DE ALPACA MARKETS
(historical EOD diario, free tier) en lugar de yfinance fresco O de la
cache parquet. Objetivo: TRIANGULACION de vendor independiente para el
veredicto SMC (OB + BOS/CHoCH).

POR QUE ALPACA y no yfinance:
  - Datos diarios EOD del free tier son directos de exchange (IEX/SIP),
    split+dividend ajustados (adjustment=all ~ yfinance auto_adjust),
    timezone America/New_York -> alinean con el backtest diario.
  - Es un VENDOR DISTINTO a yfinance (la cache canonica del repo es
    yfinance-derivada via data_ingestion.py), asi que un holdout que
    coincida aca hace el veredicto negativo robusto al origen de datos.
  - El repo YA tiene el cliente Alpaca (app/core/execution_costs.py,
    AlpacaPaperClient) y el slot de credenciales en config.py
    (ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY). Reusamos ese
    esquema de auth (headers APCA-API-KEY-ID / APCA-API-SECRET-KEY) en
    el host de DATOS (data.alpaca.markets).

AISLAMIENTO (strict, igual que los otros explore_*):
  - Solo este archivo nuevo (untracked). CERO edicion a archivos existentes.
  - CERO commit/push. Un solo artifact .txt en data/cache.
  - NO es veredicto: requeriria pre-registro + gate (PBO<0.10, DSR>=0.95,
    Bonferroni/CSCV, holdout sellado 2025-09-01). Es triangulacion.

CREDENCIALES (regla del repo: NUNCA en chat):
  - Se leen de backend/.env (gitignored) o de os.environ.
  - Si no estan, el script avisa claro y sale (no crashea).
  - Boris las pone en backend/.env localmente (no por chat):
        ALPACA_PAPER_API_KEY=...
        ALPACA_PAPER_SECRET_KEY=...
========================================================================
"""
import os
import sys
import datetime as dt

import numpy as np
import pandas as pd
import requests
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ORIGINAL = os.path.join(HERE, "explore_smc_ob_signal.py")

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
START = _orig.START
END = _orig.END

DATA_HOST = "https://data.alpaca.markets"
# Free tier EOD: probar IEX primero, caer a SIP si IEX no trae suficientes bars.
FEEDS = ["iex", "sip"]


def load_creds():
    """Carga ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY desde backend/.env
    (gitignored) o desde os.environ. No imprime valores jamas."""
    env_path = os.path.join(BACKEND, ".env")
    if os.path.exists(env_path):
        with open(env_path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return (
        os.environ.get("ALPACA_PAPER_API_KEY", ""),
        os.environ.get("ALPACA_PAPER_SECRET_KEY", ""),
    )


def load_alpaca(sym: str, api_key: str, secret_key: str):
    """Descarga bars diarios EOD de Alpaca para un simbolo.
    Traduce BRK-B -> BRK.B (la API de datos rechaza el guion con 400).
    Devuelve DataFrame [open,high,low,close] indice datetime naive, o None."""
    from_sym = sym.replace("-", ".")
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    bars = []
    used_feed = None
    for feed in FEEDS:
        bars = []
        url = f"{DATA_HOST}/v2/stocks/{from_sym}/bars"
        params = {
            "timeframe": "1Day",
            "start": START,
            "end": END,
            "adjustment": "all",
            "feed": feed,
            "limit": 10000,
        }
        while url:
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            except Exception as e:  # noqa: BLE001
                print(f"  [load] {sym} request error ({feed}): {type(e).__name__}: {e}")
                break
            if resp.status_code != 200:
                # 401/403 => sin acceso (subscripcion) o credencial mala.
                # Probar el siguiente feed antes de descartar.
                print(f"  [load] {sym} HTTP {resp.status_code} ({feed}): "
                      f"{resp.text[:120]}")
                break
            j = resp.json()
            bars.extend(j.get("bars", []))
            npt = j.get("next_page_token")
            if npt:
                params = {"page_token": npt}
                url = f"{DATA_HOST}/v2/stocks/{from_sym}/bars"
            else:
                url = None
        if len(bars) >= WARMUP + 10:
            used_feed = feed
            break

    if not used_feed:
        print(f"  [load] {sym} sin barras suficientes (feeds probados: {FEEDS})")
        return None

    recs = [{"ts": b["t"], "open": b["o"], "high": b["h"],
             "low": b["l"], "close": b["c"]} for b in bars]
    df = pd.DataFrame.from_records(recs)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts").sort_index()
    df = df[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if len(df) < WARMUP + 10:
        print(f"  [load] {sym} muy corto ({len(df)} barras, feed={used_feed})")
        return None
    print(f"  [load] {sym} OK {len(df)} barras (feed={used_feed}, "
          f"{df.index[0].date()} -> {df.index[-1].date()})")
    return df



def main():
    api_key, secret_key = load_creds()
    if not api_key or not secret_key:
        print("=" * 78)
        print("FALTAN CREDENCIALES ALPACA -> no se puede descargar data.")
        print("Pone en backend/.env (gitignored, NO por chat):")
        print("    ALPACA_PAPER_API_KEY=...")
        print("    ALPACA_PAPER_SECRET_KEY=...")
        print("(Tomadas de tu nota de Apple Notes 'Alpaca Paper'.)")
        print("=" * 78)
        sys.exit(1)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(BACKEND, "data", "cache",
                            f"explore_smc_ob_alpaca_{ts}.txt")
    lines = []

    def log(s=""):
        lines.append(str(s))
        print(s)

    log("=" * 78)
    log("SMC OB SIGNAL — DATA SOURCE: ALPACA MARKETS (EOD diario, free tier)")
    log("=" * 78)
    log(f"  universo      : {len(SYMBOLS)} simbolos")
    log(f"  rango pedido  : {START} -> {END}")
    log(f"  warmup        : {WARMUP}b")
    log(f"  in-sample end : {IN_SAMPLE_END.date()} | holdout start: {HOLDOUT_START.date()}")

    log("")
    log("-" * 78)
    log("CAUSALITY CHECK (market_structure_history, AAPL)")
    log("-" * 78)
    causality_ok = False
    aapl = load_alpaca("AAPL", api_key, secret_key)
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
    log("BACKTEST (50 simbolos, Alpaca EOD)")
    log("-" * 78)
    all_trades = []
    failed = []
    for i, sym in enumerate(SYMBOLS, 1):
        df = load_alpaca(sym, api_key, secret_key)
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
    log("COMPARACION vs YFINANCE-CACHE (explore_smc_ob_parquet)")
    log("=" * 78)
    log("  yfinance-cache HOLDOUT: n=72, win=25.00%, mean_R=-0.2789, sharpe=-1.871")
    log(f"  alpaca          HOLDOUT: n={m_ho['n_trades']}, "
        f"win={m_ho['win_rate']:.2f}%, mean_R={m_ho['mean_R']:.4f}, "
        f"sharpe={m_ho['sharpe_eq']:.3f}")
    if m_ho["n_trades"] == 72 and abs(m_ho["sharpe_eq"] - (-1.871)) < 0.05:
        log("  => COINCIDENCIA: veredicto negativo SMC robusto al vendor de datos.")
    else:
        log("  => DIVERGENCIA: revisar artifact y posible artefacto de datos.")

    log("")
    log("=" * 78)
    log("LIMITACIONES")
    log("=" * 78)
    log("  * Exploratorio: NO es veredicto. Requeriria pre-registro + gate")
    log("    (PBO<0.10, DSR>=0.95, Bonferroni/CSCV, holdout sellado 2025-09-01).")
    log(f"  * Causalidad (market_structure_history): "
        f"{'PASS (sin look-ahead)' if causality_ok else 'NO VERIFICADA / FAIL'}")
    log("  * DATA: Alpaca Markets EOD diario (free tier, adjustment=all).")
    log("  * Misma senal/metricas que explore_smc_ob_signal.py.")
    log(f"  * Warmup={WARMUP}b. Simbolos fallidos: {failed if failed else 'ninguno'}.")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    log("")
    log(f"Artifact: {out_path}")


if __name__ == "__main__":
    main()

