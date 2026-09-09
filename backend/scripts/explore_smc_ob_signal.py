#!/usr/bin/env python3
"""
explore_smc_ob_signal.py
========================================================================
EXPLORATORY backtest of a Smart Money Concepts (SMC) signal -- ORDER BLOCKS
(OB) + BOS/CHoCH trend -- built on the EXISTING repo module
``backend/app/core/market_structure.py``, using its CAUSAL per-date function
``market_structure_history`` (NOT ``analyze_market_structure``).

PURPOSE (per Boris): empirically PROBE whether this SMC OB signal has any
historical edge, isolated from ongoing work. EXPLORATION, NOT a registered
trial. No veredict CUMPLE/NO_CUMPLE. A real verdict needs pre-registration +
gate (PBO<0.10, DSR>=0.95, Bonferroni/CSCV, sealed holdout 2025-09-01).

ISOLATION (strict): only this script created; no existing file edited; no git
commit/push; nothing written to trial_registry.json; only ONE .txt artifact.

DATA SOURCE: Stooq CSV blocked by anti-bot JS challenge -> fallback yfinance
(1.7.0, works under pandas 3.0.5 / numpy 2.5.2). yf.download called directly
(NOT data_ingestion.download_data) to avoid 50 parquet caches and to capture
the holdout (yfinance `end` is exclusive).

SIGNAL (pre-stated): per day t from market_structure_history(df):
  LONG  iff ob_type==1 AND not ob_mitigated AND close[t] <= ob_top[t]
             AND (smc_trend[t]==1 OR bos_direction[t]==1)
  SHORT iff ob_type==-1 AND not ob_mitigated AND close[t] >= ob_bottom[t]
             AND (smc_trend[t]==-1 OR bos_direction[t]==-1)
  Entry OPEN t+1. One position per symbol. Stop = ob_bottom/Top +/- 0.2*ATR14.
  Target 2R. Exit stop/target/max20bars (stop first on same-bar). risk<=0 -> skip.
  ATR14 (Wilder) inline; indicators.py NOT imported.

SPLIT: IN-SAMPLE entry<=2025-08-31 | HOLDOUT entry>=2025-09-01.

CAUSALITY CHECK: for AAPL at several t compare
  market_structure_history(df).iloc[t]  vs
  market_structure_history(df.iloc[:t+1]).iloc[t].
  Identical => state at t depends only on data <= t => no look-ahead.
"""
import os
import datetime as dt

import numpy as np
import pandas as pd
import yfinance as yf
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
MS_PATH = os.path.join(BACKEND, "app", "core", "market_structure.py")

_spec = importlib.util.spec_from_file_location("ms_module", MS_PATH)
_ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ms)
market_structure_history = _ms.market_structure_history

SYMBOLS = [
    "SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "BRK-B", "LLY", "JPM", "WMT", "V", "UNH", "XOM", "MA", "ORCL", "PG", "COST", "HD",
    "JNJ", "ABBV", "BAC", "MRK", "CRM", "KO", "ADBE", "PEP", "AMD", "NFLX", "TMO", "CVX",
    "CSCO", "ACN", "MCD", "IBM", "LIN", "QCOM", "GE", "INTU", "PM", "CMCSA", "DIS", "TXN",
    "CAT", "AMGN", "PFE", "SPGI",
]

START = "2015-01-01"
END = "2026-12-31"
WARMUP = 120
NEIGHBOR = 5
ATR_WIN = 14
MAX_BARS = 20
R_MULT = 2.0
IN_SAMPLE_END = pd.Timestamp("2025-08-31")
HOLDOUT_START = pd.Timestamp("2025-09-01")
RISK_PCT = 0.01


def load_symbol(sym: str):
    try:
        df = yf.download(sym, start=START, end=END, progress=False,
                         auto_adjust=True, threads=False)
    except Exception as e:  # noqa: BLE001
        print(f"  [load] {sym} yf.download failed: {type(e).__name__}: {e}")
        return None
    if df is None or (hasattr(df, "empty") and df.empty):
        print(f"  [load] {sym} empty")
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
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


def atr14(df: pd.DataFrame) -> np.ndarray:
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    prev = np.roll(c, 1)
    prev[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    atr = np.full(len(tr), np.nan)
    if len(tr) >= ATR_WIN:
        atr[ATR_WIN - 1] = tr[:ATR_WIN].mean()
        for i in range(ATR_WIN, len(tr)):
            atr[i] = (atr[i - 1] * (ATR_WIN - 1) + tr[i]) / ATR_WIN
    return atr


def backtest_symbol(df: pd.DataFrame):
    n = len(df)
    atr = atr14(df)
    ms = market_structure_history(df, atr=None, neighbor=NEIGHBOR)
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    ob_type = ms["ob_type"].to_numpy()
    ob_top = ms["ob_top"].to_numpy()
    ob_bottom = ms["ob_bottom"].to_numpy()
    ob_mit = ms["ob_mitigated"].to_numpy()
    trend = ms["smc_trend"].to_numpy()
    bos = ms["bos_direction"].to_numpy()

    trades = []
    cooldown = -1
    for t in range(WARMUP, n - 1):
        if t < cooldown:
            continue
        long_sig = (ob_type[t] == 1 and not ob_mit[t]
                    and np.isfinite(ob_top[t]) and c[t] <= ob_top[t]
                    and (trend[t] == 1 or bos[t] == 1))
        short_sig = (ob_type[t] == -1 and not ob_mit[t]
                     and np.isfinite(ob_bottom[t]) and c[t] >= ob_bottom[t]
                     and (trend[t] == -1 or bos[t] == -1))
        if not (long_sig or short_sig):
            continue

        side = 1 if long_sig else -1
        entry_idx = t + 1
        if entry_idx >= n:
            break
        entry = o[entry_idx]
        a = atr[entry_idx]
        if not np.isfinite(a) or a <= 0:
            continue
        if side == 1:
            stop = ob_bottom[t] - 0.2 * a
            risk = entry - stop
            if risk <= 0:
                continue
            target = entry + R_MULT * risk
        else:
            stop = ob_top[t] + 0.2 * a
            risk = stop - entry
            if risk <= 0:
                continue
            target = entry - R_MULT * risk

        exit_idx = None
        exit_price = None
        R = None
        end_k = min(t + 1 + MAX_BARS, n - 1)
        for k in range(t + 1, end_k + 1):
            if side == 1:
                if l[k] <= stop:
                    exit_idx, exit_price, R = k, stop, -1.0
                    break
                if h[k] >= target:
                    exit_idx, exit_price, R = k, target, R_MULT
                    break
            else:
                if h[k] >= stop:
                    exit_idx, exit_price, R = k, stop, -1.0
                    break
                if l[k] <= target:
                    exit_idx, exit_price, R = k, target, R_MULT
                    break
        if exit_idx is None:  # timeout at end_k
            exit_idx = end_k
            exit_price = c[end_k]
            R = (exit_price - entry) / risk if side == 1 else (entry - exit_price) / risk

        trades.append(dict(
            symbol=df.attrs.get("symbol", "?"),
            side=side, entry_idx=entry_idx, exit_idx=exit_idx,
            entry=entry, exit=exit_price, stop=stop, target=target, risk=risk,
            R=R, n_bars=exit_idx - entry_idx,
            entry_date=df.index[entry_idx], exit_date=df.index[exit_idx],
        ))
        cooldown = exit_idx  # ignore new signals until this trade closes
    return trades


def causality_check(df: pd.DataFrame, t_values):
    cols = ["ob_type", "ob_top", "ob_bottom", "ob_mitigated", "bos_direction",
            "bos_level", "choch_detected", "smc_trend", "fvg_type",
            "nearest_swing_low", "nearest_resistance"]
    full = market_structure_history(df, atr=None, neighbor=NEIGHBOR)
    mism = []
    for t in t_values:
        if t >= len(df):
            continue
        trunc = market_structure_history(df.iloc[: t + 1], atr=None, neighbor=NEIGHBOR)
        rf = full.iloc[t]
        rt = trunc.iloc[-1]  # last row of truncated == row t of that run
        for col in cols:
            a, b = rf[col], rt[col]
            if pd.isna(a) and pd.isna(b):
                continue
            if pd.isna(a) or pd.isna(b):
                mism.append((t, col, "nan_mismatch",
                             float(a) if pd.notna(a) else None,
                             float(b) if pd.notna(b) else None))
                continue
            if abs(float(a) - float(b)) > 1e-9:
                mism.append((t, col, "value_mismatch", float(a), float(b)))
    return (len(mism) == 0), mism


def metrics_for(trades):
    if not trades:
        return dict(n_trades=0, win_rate=float("nan"), mean_R=float("nan"),
                    sharpe_eq=float("nan"), max_dd_pct=float("nan"))
    R = np.array([t["R"] for t in trades])
    win = float(np.mean(R > 0) * 100)
    mean_R = float(np.mean(R))
    by_sym = {}
    for tr in trades:
        by_sym.setdefault(tr["symbol"], []).append(tr)
    all_dates = pd.bdate_range(
        min(tr["entry_date"] for tr in trades),
        max(tr["exit_date"] for tr in trades),
    )
    eq_cols = []
    for sym, tlist in by_sym.items():
        s = pd.Series(1.0, index=all_dates)
        for tr in tlist:
            d = tr["exit_date"]
            if d in s.index:
                s.loc[d:] = s.loc[d:] * (1.0 + tr["R"] * RISK_PCT)
        eq_cols.append(s)
    if eq_cols:
        port = pd.concat(eq_cols, axis=1).mean(axis=1)
        rets = port.pct_change().dropna()
        sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if (len(rets) > 1 and rets.std() > 0) else float("nan")
        running_max = port.cummax()
        max_dd = float(((port - running_max) / running_max).min() * 100)
    else:
        sharpe, max_dd = float("nan"), float("nan")
    return dict(n_trades=len(trades), win_rate=win, mean_R=mean_R,
                sharpe_eq=sharpe, max_dd_pct=max_dd)


def main():
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_dir = os.path.join(BACKEND, "data", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    out_path = os.path.join(cache_dir, f"explore_smc_ob_{stamp}.txt")

    lines = []
    def log(s=""):
        lines.append(s)
        print(s)

    log("=" * 78)
    log("EXPLORATORY SMC ORDER-BLOCK SIGNAL BACKTEST (no verdict)")
    log("=" * 78)
    log(f"Generated : {dt.datetime.now().isoformat(timespec='seconds')}")
    log(f"Universe  : {len(SYMBOLS)} canonical symbols")
    log(f"Window    : {START} -> {END}")
    log(f"Split     : IN-SAMPLE entry<= {IN_SAMPLE_END.date()} | HOLDOUT entry>= {HOLDOUT_START.date()}")
    log(f"Warmup    : {WARMUP}b | Max hold: {MAX_BARS}b | Target: {R_MULT}R | ATR{ATR_WIN} Wilder")
    log(f"Data src  : yfinance (Stooq blocked by anti-bot JS)")
    log(f"Detector  : market_structure_history (CAUSAL)")
    log("")

    log("-" * 78)
    log("CAUSALITY CHECK (no look-ahead): full vs truncated-at-t+1")
    log("-" * 78)
    aapl = load_symbol("AAPL")
    causality_ok = None
    if aapl is None:
        log("  AAPL download failed -> causality NOT verified (limitation).")
        causality_ok = False
    else:
        aapl.attrs["symbol"] = "AAPL"
        n = len(aapl)
        tvals = sorted(set(int(x) for x in [max(WARMUP + 50, n // 4), n // 2,
                                            3 * n // 4, min(n - 20, 9 * n // 10)]))
        ok, mism = causality_check(aapl, tvals)
        causality_ok = ok
        log(f"  AAPL bars={n}; checked t={tvals}")
        if ok:
            log("  PASS: state at t identical with future truncated -> NO look-ahead.")
        else:
            log(f"  FAIL: {len(mism)} mismatches. First few:")
            for m in mism[:10]:
                log(f"    t={m[0]} col={m[1]} {m[2]} a={m[3]} b={m[4]}")
    log("")

    log("-" * 78)
    log("BACKTEST (50 symbols)")
    log("-" * 78)
    all_trades = []
    failed = []
    for i, sym in enumerate(SYMBOLS, 1):
        df = load_symbol(sym)
        if df is None:
            failed.append(sym)
            continue
        df.attrs["symbol"] = sym
        trs = backtest_symbol(df)
        all_trades.extend(trs)
        log(f"  [{i:2d}/50] {sym:6s} trades={len(trs)}")

    log("")
    log(f"Symbols with data : {len(SYMBOLS) - len(failed)} / {len(SYMBOLS)}")
    if failed:
        log(f"Symbols FAILED    : {failed}")
    log(f"Total trades      : {len(all_trades)}")

    insample = [t for t in all_trades if t["entry_date"] <= IN_SAMPLE_END]
    holdout = [t for t in all_trades if t["entry_date"] >= HOLDOUT_START]

    log("")
    log("=" * 78)
    log("METRICS - IN-SAMPLE (entry <= 2025-08-31)")
    log("=" * 78)
    m_in = metrics_for(insample)
    log(f"  n_trades   : {m_in['n_trades']}")
    log(f"  win_rate   : {m_in['win_rate']:.2f}%")
    log(f"  mean_R     : {m_in['mean_R']:.4f}")
    log(f"  sharpe_eq  : {m_in['sharpe_eq']:.3f}  (daily equity, ann sqrt(252), 1% risk/trade)")
    log(f"  max_dd_pct : {m_in['max_dd_pct']:.2f}%")

    log("")
    log("=" * 78)
    log("METRICS - HOLDOUT (entry >= 2025-09-01, SEALED OUT-OF-SAMPLE)")
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
    log("  * Data: yfinance (Stooq CSV bloqueado por challenge anti-bot JS).")
    log("  * yfinance auto_adjust=True (precios ajustados por splits/dividendos).")
    log("  * ATR14 Wilder inline; entry open t+1; stop ob_bottom/Top +/-0.2ATR;")
    log("    target 2R; salida stop/target/max20b; un trade por simbolo.")
    log("  * Entrada LONG close[t]<=ob_top[t]; SHORT close[t]>=ob_bottom[t] (texto")
    log("    pre-stated) -> permite entrar ligeramente fuera de la caja exacta del OB;")
    log("    trades con riesgo<=0 se descartan.")
    log("  * Equity/Sharpe asume 1% riesgo por trade, equal-weight por simbolo, sin")
    log("    tope de apalancamiento cruzado (trades solapados pueden exceder 100% de")
    log("    notional) -- simplificacion para exploracion.")
    log(f"  * Warmup={WARMUP}b. Symbols fallidos: {failed if failed else 'ninguno'}.")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    log("")
    log(f"Artifact: {out_path}")


if __name__ == "__main__":
    main()
