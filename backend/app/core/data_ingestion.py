import os
from datetime import datetime

import pandas as pd
import yfinance as yf

CACHE_DIR = "data/cache"

# A0 (PLAN_REMEDIO_BRECHAS_20260903): el harness de integridad corre en CADA
# actualización de cache, no como pasada única. La reconciliación fresca
# completa de 102 símbolos en cada corrida duplicaría las llamadas a Yahoo
# del updater; por eso el hook diario hace la parte barata (sanidad de
# retornos + huecos con calendario, cero red) y la descarga fresca de
# verificación SOLO para los símbolos que levantaron flag — donde la
# especificación exige re-descarga de todos modos. reconcile_cache() del
# módulo sigue existiendo para la pasada full cuando se quiera.
INTEGRITY_CHECK_ON_UPDATE = True


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex or tuple columns from yfinance 1.x."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    elif any(isinstance(c, tuple) for c in df.columns):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def _integrity_hook(ticker: str, df: pd.DataFrame, cache_path: str) -> pd.DataFrame:
    """A0: sanidad + huecos sobre el cache recién actualizado (cero red).

    Corre al final de download_data cuando el cache existe y tiene filas.
    La parte con red (reconcile vs fresco) la dispara el validador cuando
    un símbolo tiene hard-flag: un |retorno| >20% en large-cap es la firma
    de la contaminación documentada (COMPARACION §3) y paga la descarga de
    verificación. Todo falla blando: el hook jamás rompe la actualización
    de precios — un error de integridad se loguea y se sigue.

    Devuelve el DataFrame a devolver (el saneado si hubo reparación).
    """
    if not INTEGRITY_CHECK_ON_UPDATE or df is None or len(df) == 0:
        return df
    try:
        from app.core.cache_integrity import (
            find_intermediate_gaps,
            reconcile_symbol,
            validate_returns,
        )
    except ImportError:  # pragma: no cover — módulo propio, siempre presente en backend
        return df

    flags = validate_returns(df, ticker)
    hard = [f for f in flags if f["level"] == "hard"]
    if hard:
        for f in hard:
            print(
                f"[cache_integrity] {ticker} SANIDAD: retorno {f['return']*100:+.1f}% "
                f"el {f['date']} supera {f['threshold']*100:.0f}% ({f['level']}) — "
                "verificar contra descarga fresca"
            )
        # hard-flag: paga la reconciliación con descarga fresca de HOY para
        # este símbolo (contaminación -> re-descarga completa; mosaico/hueco
        # -> reparación dirigida). yf.download directo — el mismo canal del
        # updater, misma base de reajuste del día.
        reconcile_symbol(
            ticker,
            os.path.dirname(cache_path),
            downloader=yf.download,
            start="2015-01-01",
        )
        # el parquet pudo cambiar (re-descarga): releer para devolver lo sano
        if os.path.exists(cache_path):
            repaired = pd.read_parquet(cache_path)
            if len(repaired):
                repaired = _flatten_columns(repaired)
                repaired.columns = [str(c).lower() for c in repaired.columns]
                return repaired
        return df
    gaps = find_intermediate_gaps(df)
    if gaps:
        print(
            f"[cache_integrity] {ticker} HUECOS: {len(gaps)} fechas de mercado "
            f"ausentes en el rango del archivo ({gaps[0]}..{gaps[-1]}) — "
            "reparando el tramo (no solo el extremo derecho)"
        )
        reconcile_symbol(
            ticker,
            os.path.dirname(cache_path),
            downloader=yf.download,
            start="2015-01-01",
        )
        if os.path.exists(cache_path):
            repaired = pd.read_parquet(cache_path)
            if len(repaired):
                repaired = _flatten_columns(repaired)
                repaired.columns = [str(c).lower() for c in repaired.columns]
                return repaired
    return df


def download_data(ticker: str, start="2010-01-01", end=None) -> pd.DataFrame:
    end = end or datetime.today().strftime("%Y-%m-%d")
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = f"{CACHE_DIR}/{ticker}.parquet"

    if os.path.exists(cache_path):
        df = pd.read_parquet(cache_path)
        df = _flatten_columns(df)

        # Edge: cache file exists but is empty (corrupt/truncated write) -> treat as miss
        if df.empty:
            print(f"[data_ingestion] {ticker} cache empty, full download {start} -> {end}")
            df = yf.download(ticker, start=start, end=end, progress=False)
            if not df.empty:
                df = _flatten_columns(df)
                df.to_parquet(cache_path)
                print(f"[data_ingestion] {ticker} full download: refreshed {len(df)} rows ({df.index[0].date()} -> {df.index[-1].date()})")
            else:
                print(f"[data_ingestion] {ticker} full download: attempted but yfinance returned empty")
            df = _flatten_columns(df)
            df.columns = [str(c).lower() for c in df.columns]
            return df

        # ------------------------------------------------------------------
        # Backfill: cache starts later than requested start
        # Threshold rationale: daily updater must attempt when gap >= 1 calendar
        # day. Old value >7 deferred refresh for a week, so nightly runs with
        # gap 1-7 silently did nothing; stale cache (0-8 days) was invisible
        # because "no attempt" and "attempted but weekend empty" looked identical.
        # >0 and >=1 are equivalent for integer .days, but >=1 reads intent
        # clearer ("at least one full day behind") and matches the daily schedule.
        # Weekend/holiday gap=1 where yfinance returns empty is OK — we log
        # "attempted but empty" instead of suppressing the attempt.
        # ------------------------------------------------------------------
        first_date = pd.Timestamp(df.index[0])
        start_ts = pd.Timestamp(start)
        backfill_gap = (first_date - start_ts).days
        if backfill_gap >= 1:
            print(
                f"[data_ingestion] {ticker} backfill: gap {backfill_gap}d "
                f"(cache {first_date.date()} > start {start_ts.date()}), "
                f"attempting download {start} -> {first_date.strftime('%Y-%m-%d')}"
            )
            old = yf.download(ticker, start=start, end=first_date.strftime("%Y-%m-%d"), progress=False)
            if old.empty:
                print(f"[data_ingestion] {ticker} backfill: attempted but yfinance returned empty (weekend/holiday or no data)")
            else:
                old = _flatten_columns(old)
                before_len = len(df)
                new_rows = old[~old.index.isin(df.index)]
                if new_rows.empty:
                    print(f"[data_ingestion] {ticker} backfill: attempted but no new rows after dedup (all overlapping)")
                else:
                    df = pd.concat([new_rows, df])
                    df = df.sort_index()
                    df = _flatten_columns(df)
                    df.to_parquet(cache_path)
                    print(
                        f"[data_ingestion] {ticker} backfill: refreshed {len(df) - before_len} rows "
                        f"({new_rows.index[0].date()} -> {new_rows.index[-1].date()}, "
                        f"cache now {df.index[0].date()} -> {df.index[-1].date()})"
                    )
        else:
            print(
                f"[data_ingestion] {ticker} backfill: no backfill needed, gap {backfill_gap}d "
                f"(cache {first_date.date()} <= start {start_ts.date()})"
            )

        # ------------------------------------------------------------------
        # Refresh: cache ends before requested end — same threshold/signal logic
        # ------------------------------------------------------------------
        last_date = pd.Timestamp(df.index[-1])
        end_ts = pd.Timestamp(end)
        refresh_gap = (end_ts - last_date).days
        if refresh_gap >= 1:
            print(
                f"[data_ingestion] {ticker} refresh: gap {refresh_gap}d "
                f"(cache {last_date.date()} -> end {end_ts.date()}), "
                f"attempting download {last_date.strftime('%Y-%m-%d')} -> {end}"
            )
            new = yf.download(ticker, start=last_date.strftime("%Y-%m-%d"), end=end, progress=False)
            if new.empty:
                print(
                    f"[data_ingestion] {ticker} refresh: attempted but yfinance returned empty "
                    f"(weekend/holiday or no data), cache remains {last_date.date()}"
                )
            else:
                new = _flatten_columns(new)
                before_len = len(df)
                before_last = last_date
                new_rows = new[~new.index.isin(df.index)]
                if new_rows.empty:
                    print(
                        f"[data_ingestion] {ticker} refresh: attempted but no new rows after dedup "
                        f"(all overlapping), cache remains {before_last.date()}"
                    )
                else:
                    df = pd.concat([df, new_rows])
                    df = df.sort_index()
                    df = _flatten_columns(df)
                    df.to_parquet(cache_path)
                    print(
                        f"[data_ingestion] {ticker} refresh: refreshed {len(df) - before_len} rows "
                        f"({new_rows.index[0].date()} -> {new_rows.index[-1].date()}, "
                        f"cache {before_last.date()} -> {df.index[-1].date()})"
                    )
        else:
            print(
                f"[data_ingestion] {ticker} refresh: no refresh needed, gap {refresh_gap}d "
                f"(cache up-to-date {last_date.date()} >= end {end_ts.date()})"
            )
    else:
        print(f"[data_ingestion] {ticker} cache miss: downloading full range {start} -> {end}")
        df = yf.download(ticker, start=start, end=end, progress=False)
        if not df.empty:
            df = _flatten_columns(df)
            df.to_parquet(cache_path)
            print(f"[data_ingestion] {ticker} cache miss: refreshed {len(df)} rows ({df.index[0].date()} -> {df.index[-1].date()})")
        else:
            print(f"[data_ingestion] {ticker} cache miss: attempted but yfinance returned empty")

    df = _flatten_columns(df)
    df.columns = [str(c).lower() for c in df.columns]

    # A0: el harness de integridad queda activo en cada actualización de cache.
    df = _integrity_hook(ticker, df, f"{CACHE_DIR}/{ticker}.parquet")
    return df


def load_universe(tickers: list, start: str, end: str) -> dict:
    data = {}
    for t in tickers:
        df = download_data(t, start, end)
        if len(df) > 200:
            data[t] = df
    return data
