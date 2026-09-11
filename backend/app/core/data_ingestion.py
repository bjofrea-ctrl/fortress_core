import glob
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
import yfinance as yf

CACHE_DIR = "data/cache"

# TASK_WARMUP_PARALELO_20260909 (Frente 2): workers para load_universe
# paralelo. I/O-bound (yfinance/parquet) → threads, no procesos. 10 =
# punto medio del rango 8-12 del ticket. max_workers=1 restaura secuencial
# (reversión sin deploy).
LOAD_UNIVERSE_MAX_WORKERS = 10

# A0 (PLAN_REMEDIO_BRECHAS_20260903): el harness de integridad corre en CADA
# actualización de cache, no como pasada única. La reconciliación fresca
# completa de 102 símbolos en cada corrida duplicaría las llamadas a Yahoo
# del updater; por eso el hook diario hace la parte barata (sanidad de
# retornos + huecos con calendario, cero red) y la descarga fresca de
# verificación SOLO para los símbolos que levantaron flag — donde la
# especificación exige re-descarga de todos modos. reconcile_cache() del
# módulo sigue existiendo para la pasada full cuando se quiera.
INTEGRITY_CHECK_ON_UPDATE = True

# --------------------------------------------------------------------------
# PERF (PRE_REG_REBUILD_531S_MEMOIZE_20260910): tres cortes al costo del hook.
#
# (1) MEMOIZE por (mtime, size) del parquet. La reconciliación es idempotente
#     en RESULTADO (reconciliar bytes idénticos no muta nada — medido: 0
#     re-descargas en 2ª pasada) pero NO en COSTO: sin memo, cada rebuild
#     intradía (TTL 300s ⇒ hasta 12×/hora) repaga el reconcile CPU-bound
#     completo. Invalidación natural: cualquier write real (updater nocturno,
#     repair, re-descarga) cambia mtime/size ⇒ memo caído ⇒ el hook completo
#     corre otra vez. La verificación NO se elimina: corre la primera vez del
#     día y tras cada parquet tocado. Mismo espíritu que _CONTEXT_CACHE_TTL:
#     verificar sí, bloquear no.
_INTEGRITY_MEMO: "dict[str, tuple[float, int, pd.DataFrame]]" = {}

# (2) VENTANA móvil (ruedas) que dispara el reconcile por hard-flag. Un
#     hard-flag HISTÓRICO (split REGN 2018, volatilidad ^VIX, earnings ISRG)
#     es legítimo y ya fue confirmado; no paga re-descarga 2015->hoy en cada
#     rebuild. Solo un hard-flag en las últimas N ruedas (la ventana del
#     updater diario) se trata como sospecha NUEVA y dispara la verificación
#     contra descarga fresca. El doc midió 106/109 símbolos con hard-flags
#     históricos legítimos pagando reconcile en cada rebuild.
INTEGRITY_HARDFLAG_WINDOW_ROUNDS = 10

# (3) CACHE perezoso de known_trading_days (fechas presentes en ≥1 símbolo del
#     cache): auto-exclusión de cierres no programables (duelos presidenciales
#     2018-12-05/2025-01-09, Sandy 2012-10-29/30) que el calendario NYSE no
#     modela. find_intermediate_gaps(known_trading_days=...) ya los excluye; el
#     hook los pasaba como None ⇒ 25 símbolos re-intentando una reparación que
#     nunca prospera (440 intentos, 0 exitosos). El conjunto cambia a lo sumo
#     1×/día ⇒ se re-computa una vez por día por cache_dir.
_KNOWN_DAYS_CACHE: "dict[tuple[str, str], set]" = {}


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex or tuple columns from yfinance 1.x."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    elif any(isinstance(c, tuple) for c in df.columns):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def _known_trading_days_for(cache_dir: str) -> set:
    """Fechas de mercado presentes en AL MENOS UN parquet del cache.

    Alimenta find_intermediate_gaps(known_trading_days=...) para que un cierre
    que ningún símbolo tiene (duelo presidencial, Sandy) NO se reporte como
    hueco y dispare una reparación eterna. Se cachea por (cache_dir, fecha de
    hoy): el conjunto cambia a lo sumo 1x/dia (append nocturno) y el hook ya
    esta memoizado por mtime, asi que leer los parquets 1x/dia es despreciable.
    """
    if not cache_dir or not os.path.isdir(cache_dir):
        return set()
    key = (cache_dir, datetime.now().date().isoformat())
    cached = _KNOWN_DAYS_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from app.core.cache_integrity import _market_days_present_in_cache
    except ImportError:  # pragma: no cover - modulo propio, siempre presente
        return set()
    syms = [
        os.path.basename(p)[: -len(".parquet")]
        for p in glob.glob(os.path.join(cache_dir, "*.parquet"))
    ]
    present = _market_days_present_in_cache(cache_dir, syms)
    _KNOWN_DAYS_CACHE.clear()          # una sola fecha valida por proceso
    _KNOWN_DAYS_CACHE[key] = present
    return present


def _integrity_hook(ticker: str, df: pd.DataFrame, cache_path: str) -> pd.DataFrame:
    """Memoize del veredicto de integridad por (mtime, size) del parquet.

    Corte del 531s (PRE_REG_REBUILD_531S_MEMOIZE_20260910): reconciliar bytes
    identicos produce un veredicto identico (cero mutaciones), asi que una 2a
    lectura del MISMO parquet saldea sin red ni CPU de reconcile. Cualquier write
    real cambia mtime/size -> memo caido -> corre el hook completo
    (_integrity_hook_full). La verificacion no se elimina: corre la primera vez
    del dia y tras cada write.
    """
    if not INTEGRITY_CHECK_ON_UPDATE or df is None or len(df) == 0:
        return df
    try:
        st = os.stat(cache_path)
        key_stat = (st.st_mtime, st.st_size)
    except OSError:
        key_stat = None
    if key_stat is not None:
        memo = _INTEGRITY_MEMO.get(cache_path)
        if memo is not None and memo[0] == key_stat[0] and memo[1] == key_stat[1]:
            # Mismos bytes que la ultima vez que este parquet se valido: veredicto
            # identico. Copiamos para que el caller no contamine el memo al mutar
            # el DataFrame en caliente.
            return memo[2].copy()
    out = _integrity_hook_full(ticker, df, cache_path)
    if key_stat is not None:
        # Re-stat: si el hook modifico el parquet (repair/re-descarga) el stat
        # cambio y memoizamos el ESTADO NUEVO (coherente con `out`); si no lo
        # toco, el stat es identico y la proxima lectura del mismo bytes saltea.
        try:
            st2 = os.stat(cache_path)
            _INTEGRITY_MEMO[cache_path] = (st2.st_mtime, st2.st_size, out)
        except OSError:
            _INTEGRITY_MEMO.pop(cache_path, None)
    return out


def _integrity_hook_full(ticker: str, df: pd.DataFrame, cache_path: str) -> pd.DataFrame:
    """A0: sanidad + huecos sobre el cache recién actualizado (cero red en el path limpio).

    Corre al final de download_data cuando el cache existe y tiene filas (siempre
    vía el wrapper memoizado _integrity_hook). La parte con red (reconcile vs
    fresco) la dispara el validador SOLO cuando un símbolo tiene hard-flag en la
    VENTANA móvil (últimas N ruedas): un |retorno| >20% reciente es la firma de la
    contaminación documentada (COMPARACION §3) y paga la descarga de verificación.
    Los hard-flags históricos legítimos (splits REGN/LRCX, earnings ISRG,
    volatilidad ^VIX) se loguean pero NO re-descargan en cada rebuild (fix 2). Los
    huecos se buscan con known_trading_days (fix 3) para no intentar reparar
    cierres que ningún símbolo tiene. Todo falla blando: el hook jamás rompe la
    actualización de precios — un error de integridad se loguea y se sigue.

    Devuelve el DataFrame a devolver (el saneado si hubo reparación).
    """
    try:
        from app.core.cache_integrity import (
            find_intermediate_gaps,
            reconcile_symbol,
            validate_returns,
        )
    except ImportError:  # pragma: no cover — módulo propio, siempre presente en backend
        return df

    cache_dir = os.path.dirname(cache_path)
    known = _known_trading_days_for(cache_dir)

    flags = validate_returns(df, ticker)
    hard = [f for f in flags if f["level"] == "hard"]
    if hard:
        # Fix 2 (H2): acotar el disparador a la ventana móvil del updater.
        window = max(1, INTEGRITY_HARDFLAG_WINDOW_ROUNDS)
        recent = {str(pd.Timestamp(d).date()) for d in df.index[-window:]}
        recent_hard = [f for f in hard if f["date"] in recent]
        for f in hard:
            en_ventana = f["date"] in recent
            accion = (
                " — verificar contra descarga fresca"
                if en_ventana
                else " — hard-flag histórico ya confirmado, no re-descarga"
            )
            print(
                f"[cache_integrity] {ticker} SANIDAD"
                f"{'[ventana]' if en_ventana else '[hist]'}: retorno {f['return']*100:+.1f}% "
                f"el {f['date']} supera {f['threshold']*100:.0f}% ({f['level']}){accion}"
            )
        if recent_hard:
            # hard-flag EN ventana: paga la reconciliación con descarga fresca de
            # HOY para este símbolo (contaminación -> re-descarga completa;
            # mosaico/hueco -> reparación dirigida). yf.download directo — el mismo
            # canal del updater, misma base de reajuste del día.
            reconcile_symbol(
                ticker,
                cache_dir,
                downloader=yf.download,
                start="2015-01-01",
                known_trading_days=known,
            )
            # el parquet pudo cambiar (re-descarga): releer para devolver lo sano
            if os.path.exists(cache_path):
                repaired = pd.read_parquet(cache_path)
                if len(repaired):
                    repaired = _flatten_columns(repaired)
                    repaired.columns = [str(c).lower() for c in repaired.columns]
                    return repaired
            return df
        # Solo hard-flags históricos confirmados: no se re-descarga (fix 2). Caemos
        # a la revisión de huecos por debajo (barata, cero red).
    gaps = find_intermediate_gaps(df, known)
    if gaps:
        print(
            f"[cache_integrity] {ticker} HUECOS: {len(gaps)} fechas de mercado "
            f"ausentes en el rango del archivo ({gaps[0]}..{gaps[-1]}) — "
            "reparando el tramo (no solo el extremo derecho)"
        )
        reconcile_symbol(
            ticker,
            cache_dir,
            downloader=yf.download,
            start="2015-01-01",
            known_trading_days=known,
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
    # Fix 09-09 (bug crítico dashboard 500): los parquets en disco tienen
    # columnas duplicadas por contaminación vieja de esquema (close+Close,
    # high+High...). Al lowercasear quedan 2 'close' literales -> df['close']
    # devuelve DataFrame no Series -> rompe validate_returns (truth value
    # of Series ambiguous). Deduplicar: quedarse con la columna que tenga
    # más valores no-nulos (la real), dropear la redundante.
    if len(df.columns) != len(set(df.columns)):
        keep = {}
        for i, c in enumerate(df.columns):
            if c not in keep or df.iloc[:, i].count() > df.iloc[:, keep[c]].count():
                keep[c] = i
        df = df.iloc[:, sorted(keep.values())]
        # Bug 09-09 (recontaminación, hallado por Boris en vivo): el dedup de
        # arriba limpiaba SOLO el df en memoria y lo devolvía así — nunca
        # reescribía el parquet. Cualquier lectura fresca posterior (otro
        # proceso, o reconcile_symbol leyendo su propia copia de disco) volvía
        # a encontrar el archivo contaminado y rompía validate_returns de
        # nuevo. Persistir el dedup es obligatorio, no solo devolverlo.
        df.to_parquet(cache_path)

    # A0: el harness de integridad queda activo en cada actualización de cache.
    df = _integrity_hook(ticker, df, f"{CACHE_DIR}/{ticker}.parquet")
    return df


def _safe_download(ticker: str, start: str, end: str):
    """download_data que nunca raisea: devuelve None y loguea el fallo.

    El lote paralelo no muere por un ticker (criterio d del pre-registro).
    """
    try:
        return download_data(ticker, start, end)
    except Exception as e:  # noqa: BLE001 — fallo aislado por ticker
        print(f"[load_universe] {ticker} ERROR aislado: {e}")
        return None


def load_universe(tickers: list, start: str, end: str,
                  max_workers: int = LOAD_UNIVERSE_MAX_WORKERS) -> dict:
    """Descarga el universo en paralelo (ThreadPoolExecutor, I/O-bound).

    Misma API de salida que la versión secuencial: dict {ticker: df} solo
    con len(df) > 200, en el MISMO orden de `tickers` (executor.map
    preserva orden). `_integrity_hook` corre dentro de `download_data` en
    cada worker; cada worker escribe su propio parquet (sin colisión, un
    archivo por ticker). El orden de escrituras a disco NO es determinístico
    (decisión pre-registrada). Fallo de un ticker → None → se excluye, el
    lote sigue. Logs por lote (inicio/fin + duración + fallos), no por ticker.
    max_workers=1 == secuencial (reversión).
    """
    tickers = list(tickers)
    print(f"[load_universe] lote inicio: {len(tickers)} tickers, workers={max_workers}")
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(lambda t: _safe_download(t, start, end), tickers))
    data = {}
    fails = 0
    for t, df in zip(tickers, results):
        if df is not None and len(df) > 200:
            data[t] = df
        else:
            fails += 1
    dt_s = time.monotonic() - t0
    print(f"[load_universe] lote fin: {len(data)}/{len(tickers)} OK, "
          f"{fails} fallos, {dt_s:.1f}s")
    return data
