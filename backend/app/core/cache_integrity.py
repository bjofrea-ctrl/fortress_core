"""A0 — Harness de integridad del cache de datos (yfinance).

PLAN_REMEDIO_BRECHAS_20260903.md §A0, especificación derivada de
COMPARACION_FUENTES_DATOS.md §10.2/§10.3 (medida, no de opinión — no reinventar).

El cache de yfinance es append-only (data_ingestion.py: el refresh solo pide
desde `last_date` en adelante y el backfill solo corrige el extremo izquierdo).
Eso permitió tres clases de defecto verificadas en production (ver COMPARACION
§3/§4/§6):

1. Contaminación cruzada: barras OHLCV COMPLETAS de otros símbolos escritas en
   archivos equivocados (38 barras confirmadas en 29 parquets, ej. KO con la
   barra de CRM: close 89.66 -> 257.54, +187% en un día). Una vez escrita, la
   barra es indeleble: los runs siguientes solo piden el extremo derecho.
2. Mosaico: bases de reajuste de dividendos mezcladas dentro de un mismo
   archivo (seams donde el ratio cache/fresco salta de 1.0087 a 1.0). El
   reajuste retroactivo de Yahoo re-escribe el pasado en cada descarga; el
   append-only congela filas viejas en la base del día que se descargaron.
3. Huecos intermedios: fechas de mercado ausentes en el medio del rango
   (64 huecos en 57/102 símbolos, ej. AKAM sin 2026-08-28). El diseño
   append-only jamás re-pide una fecha intermedia ya pasada.

Este módulo implementa las partes 1-3 del ticket (la parte 4, cross-check
Finnhub↔FMP, queda DIFERIDA hasta que FMP produzca datos — hoy 0 datos y
desborde de cuota estructural 510 > 250 calls/día, ver COMPARACION §8):

  Parte 1 — validate_returns: flag de |retorno diario| > umbral POR CLASE de
  símbolo (large-cap 0.15-0.20 del rango del spec). Barato (segundos), corre
  en cada actualización. ES UNA SEÑAL DE REVISIÓN, no acción automática: un
  large-cap puede mover ±20% real (earnings). La acción (re-descarga) sale
  del cross-check contra la descarga fresca (parte 2), que es la prueba.

  Parte 2 — reconcile_symbol / reconcile_cache: comparación cache vs
  descarga fresca del MISMO yfinance:
    (a) fila cuyo OHLCV matchea OTRO símbolo ese día (criterio del doc §3.1:
        OHLC <0.1% y volumen <1% contra la barra real del otro símbolo)
        -> BLOQUEO + re-descarga del archivo completo;
    (b) mosaico: plateaus del ratio cache/fresco (seam = salto del ratio
        entre tramos largos) -> re-descarga completa del archivo;
    (c) huecos de fechas intermedias (calendario NYSE dentro del propio
        rango del símbolo) -> re-descarga SOLO del tramo faltante.

  Parte 3 — snapshot_hash: hash SHA-256 del contenido canónico de cada
  parquet del universo, para que el pre-registro de cada trial congele el
  cache que consume (reproducibilidad contra el reajuste retroactivo).
  Funciones para el trial_registry: cache_snapshot_for_trial() genera el
  manifiesto {archivo, filas, rango, sha256} y attach_cache_snapshot()
  lo registra en la entrada del ledger.

Dónde se engancha: download_data() de data_ingestion.py llama a
run_integrity_check DESPUÉS de su refresh/backfill normal — el harness queda
activo en cada actualización de cache, no es una pasada única (§A0
Verificación: "con el harness quedando activo en cada actualización
subsiguiente").

Restricción del gate (PLAN_REMEDIO §FASE A): esto es observabilidad +
reparación dirigida del cache. NO toca la lógica de decisión del motor
(signal_engine, backtest_engine, paper_trading).

Reglas del proyecto: Python 3.9 real (nada de sintaxis 3.10+), fallar
ruidosamente ante datos inconsistentes, cero relleno artificial de precios.
"""
import hashlib
import json
import os
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:  # dateutil viene con pandas (dependencia transitiva) — usado para Pascua
    from dateutil import easter as _easter
except ImportError:  # pragma: no cover — el venv real siempre lo tiene
    _easter = None

# --------------------------------------------------------------------------
# Umbrales por clase de símbolo (Parte 1) — spec §10.2 punto 1:
# "flag de cualquier |retorno diario| > umbral por clase de símbolo
#  (large-cap: 15-20%)". El rango 15-20% del spec se implementa con DOS
# umbrales: >0.15 es `flag` (revisar) y >0.20 es `flag_hard` (contaminación
# documentada: KO +187%, CMCSA +623% — el nivel donde el doc confirma que
# era basura). Los niveles altos (high-vol) usan 0.30 (TSLA/NFLX se mueven
# ±25% real en earnings; el doc midió p999 de TSLA en 21%).
# --------------------------------------------------------------------------
RETURN_THRESHOLDS = {
    "large_cap": 0.15,
    "high_vol": 0.30,
}

# Hard-flag: umbral donde un large-cap NO se movió real (contaminación
# documentada empieza en +148% [XOM] y el flag del ticket A0 es ">20%").
HARD_THRESHOLD_LARGE_CAP = 0.20

# Símbolos high-vol del universo 102 (criterio del doc §3: los grandes
# movimiento reales de ±20-25% en earnings — TSLA/NFLX/META/AMD). El resto
# del universo es large-cap liquido.
HIGH_VOL_SYMBOLS = {"TSLA", "NFLX", "META", "AMD", "PYPL", "AVGO"}

# Tolerancias del criterio de contaminación (doc §3.1): "la barra del cache
# matchea en Open, High, Low, Close (<0.1%) Y Volume (<1%) a la barra real
# de OTRO símbolo ese mismo día".
PRICE_TOL = 0.001
VOLUME_TOL = 0.01

# Detección de mosaico (doc §4): plateaus del ratio cache/fresco. Un seam es
# un salto del ratio mediano entre dos tramos consecutivos de >=MIN_SEGMENT
# días; ratio == 1.0 con tolerancia MICRO_RUELO (el jitter ±1bp de
# re-serialización de Yahoo, doc §2.2) cuenta como sin seam.
MOSAIC_MIN_SEGMENT = 10
MOSAIC_RATIO_TOL = 0.0005

#Universo por defecto: el mismo del updater (data_updater.sh) — 7 BASE +
# NEW_UNIVERSE de fetch_universe_data.py. Se importa LAZY para evitar
# dependencia circular con scripts (scripts importa data_ingestion que
# importa este módulo).


def _universe_symbols() -> List[str]:
    """7 BASE + NEW_UNIVERSE (fuente única del proyecto, 102 símbolos)."""
    from scripts.fetch_universe_data import NEW_UNIVERSE  # noqa: PLC0415

    return ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)


def _symbol_class(symbol: str) -> str:
    return "high_vol" if symbol in HIGH_VOL_SYMBOLS else "large_cap"


def _threshold_for(symbol: str) -> float:
    return RETURN_THRESHOLDS[_symbol_class(symbol)]


# --------------------------------------------------------------------------
# Parte 1 — Validador de sanidad de retornos
# --------------------------------------------------------------------------


def validate_returns(df: pd.DataFrame, symbol: str) -> List[dict]:
    """Flag de cualquier |retorno diario| por encima del umbral de su clase.

    Corre en segundos sobre 11 años de diario. Es la señal que habría atrapado
    las 38 barras el día que entraron (24-ago): CMCSA +622.9% vs umbral
    large-cap 15% (KO +187%, XOM +148%...). Devuelve una lista de flags:

        {"symbol", "date", "return", "threshold", "level"}
        level: "hard" si supera HARD_THRESHOLD_LARGE_CAP (contaminación
        documentada) o el high_vol correspondiente; "soft" si solo supera el
        15% de revisión.

    NO re-descarga nada por sí sola: un large-cap puede mover ±20% real
    (AKAM +26.6% 2026-05-08 earnings, MRVL +32.5%). La prueba definitiva es
    el reconcile contra descarga fresca (parte 2); este flag marca QUÉ
    símbolo/fecha revisar y queda en el log de cada actualización.
    """
    if df is None or len(df) < 2:
        return []
    low = {str(c).lower(): c for c in df.columns}
    if "close" not in low:
        return []
    closes = df[low["close"]].astype(float)
    rets = closes.pct_change()
    thr = _threshold_for(symbol)
    hard = max(HARD_THRESHOLD_LARGE_CAP, RETURN_THRESHOLDS["high_vol"]) \
        if _symbol_class(symbol) == "high_vol" else HARD_THRESHOLD_LARGE_CAP
    flags = []
    for d, r in rets.items():
        if pd.isna(r):
            continue
        if abs(r) > hard:
            level = "hard"
        elif abs(r) > thr:
            level = "soft"
        else:
            continue
        flags.append({
            "symbol": symbol,
            "date": str(pd.Timestamp(d).date()),
            "return": round(float(r), 6),
            "threshold": thr,
            "level": level,
        })
    return flags


# --------------------------------------------------------------------------
# Calendario NYSE — para detección de huecos intermedios (Parte 2c)
# --------------------------------------------------------------------------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _good_friday(year: int) -> Optional[date]:
    if _easter is None:
        return None
    return _easter.easter(year) - timedelta(days=2)


def nyse_trading_days(year: int) -> List[date]:
    """Días de trading NYSE del año (regla estándar: fines de semana +
    New Year, MLK, Presidents, Good Friday, Memorial, Juneteenth (desde
    2022), July 4, Labor, Thanksgiving, Christmas, con observancia
    sábado->viernes / domingo->lunes).

    Verificado contra el cache real de SPY 2015-2026: coincide salvo 2
    cierres de duelo presidencial (Bush 2018-12-05, Carter 2025-01-09) que
    NINGÚN símbolo del universo tiene — por eso la detección de huecos
    exige además que AL MENOS UN símbolo del cache tenga la fecha (ver
    _reference_days): los cierres de mercado completos se auto-excluyen.
    """
    gf = _good_friday(year)
    hols = {date(year, 1, 1), date(year, 7, 4), date(year, 12, 25)}
    if gf is not None:
        hols.add(gf)
    if year >= 2022:
        hols.add(date(year, 6, 19))
    hols.add(_nth_weekday(year, 1, 0, 3))     # MLK: 3er lunes de enero
    hols.add(_nth_weekday(year, 2, 0, 3))     # Presidents: 3er lunes de febrero
    hols.add(_last_weekday(year, 5, 0))       # Memorial: último lunes de mayo
    hols.add(_nth_weekday(year, 9, 0, 1))     # Labor: 1er lunes de septiembre
    hols.add(_nth_weekday(year, 11, 3, 4))    # Thanksgiving: 4to jueves de noviembre
    observed = set()
    for h in hols:
        if h.weekday() == 5:
            observed.add(h - timedelta(days=1))
        elif h.weekday() == 6:
            observed.add(h + timedelta(days=1))
        else:
            observed.add(h)
    days = []
    d = date(year, 1, 1)
    while d <= date(year, 12, 31):
        if d.weekday() < 5 and d not in observed:
            days.append(d)
        d += timedelta(days=1)
    return days


# --------------------------------------------------------------------------
# Parte 2 — Reconciliación cache vs descarga fresca
# --------------------------------------------------------------------------


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas minúsculas + índice DatetimeIndex normalizado (la forma
    post-procesada que download_data devuelve y los motores consumen)."""
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    out.columns = [str(c).lower() for c in out.columns]
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.DatetimeIndex(out.index)
    out = out.sort_index()
    return out


def find_intermediate_gaps(
    df: pd.DataFrame,
    known_trading_days: Optional[set] = None,
) -> List[str]:
    """Huecos de fechas intermedias: días de mercado NYSE presentes dentro
    del rango [primera, última] fecha del propio archivo pero ausentes de él.

    `known_trading_days`: fechas (str YYYY-MM-DD o Timestamp) que AL MENOS
    UN símbolo del cache tiene — la auto-corrección del calendario para
    cierres no programables (duelos presidenciales). Si es None usa el
    calendario computado puro.

    El refresh append-only solo mira `last_date` en adelante: una fecha
    intermedia perdida (ej. AKAM 2026-08-28) no se vuelve a pedir NUNCA. Es
    exactamente lo que este detector + repair_gap_range vienen a cerrar.
    """
    if df is None or len(df) < 2:
        return []
    idx = pd.DatetimeIndex(df.index)
    lo = pd.Timestamp(idx[0]).date()
    hi = pd.Timestamp(idx[-1]).date()
    have = {pd.Timestamp(d).date() for d in idx}
    missing = []
    for year in range(lo.year, hi.year + 1):
        for d in nyse_trading_days(year):
            if d < lo or d > hi or d in have:
                continue
            if known_trading_days is not None and d not in known_trading_days:
                continue
            missing.append(d.isoformat())
    return missing


def _ohlcv_match(row_a: pd.Series, row_b: pd.Series) -> bool:
    """Criterio de contaminación del doc §3.1: Open/High/Low/Close < 0.1%
    Y Volume < 1% entre la fila del cache y la barra de OTRO símbolo.
    Recibe filas ya normalizadas (columnas minúsculas, ver _norm)."""
    for col in ("open", "high", "low", "close"):
        a, b = float(row_a[col]), float(row_b[col])
        if b == 0 or abs(a - b) / abs(b) > PRICE_TOL:
            return False
    va, vb = float(row_a["volume"]), float(row_b["volume"])
    if vb == 0 or abs(va - vb) / abs(vb) > VOLUME_TOL:
        return False
    return True


def _row_from(df: pd.DataFrame, day) -> Optional[pd.Series]:
    ts = pd.Timestamp(day)
    if ts not in df.index:
        return None
    return df.loc[ts]


def detect_cross_contamination(
    cached: pd.DataFrame,
    fresh: pd.DataFrame,
    other_symbols_fresh: Dict[str, pd.DataFrame],
    symbol: str,
) -> List[dict]:
    """(a) del spec: filas cuyo OHLCV matchea la barra de OTRO símbolo ese
    día. `cached` = lo que hay en disco; `fresh` = descarga fresca del
    MISMO símbolo; `other_symbols_fresh` = descargas frescas de los demás
    (o al menos los sospechosos por validate_returns).

    Confirma el mismo criterio del diagnóstico original (§3.1): matchea en
    OHLC <0.1% y volumen <1% contra el OTRO símbolo (la descarga fresca del
    propio símbolo diverge). Devuelve la lista de contaminaciones con el
    símbolo origen identificado.
    """
    cached = _norm(cached)
    findings = []
    for day, row in cached.iterrows():
        d = pd.Timestamp(day)
        own = _row_from(_norm(fresh), d)
        if own is None:
            continue  # la fecha no existe fresca: hueco/fin de rango, no contaminación
        own_close = float(own["close"])
        row_close = float(row["close"])
        if abs(row_close - own_close) / abs(own_close) <= PRICE_TOL:
            continue  # la fila coincide con su propio símbolo: sana
        for other, other_fresh in other_symbols_fresh.items():
            if other == symbol:
                continue
            other_row = _row_from(_norm(other_fresh), d)
            if other_row is None:
                continue
            if _ohlcv_match(row, other_row):
                findings.append({
                    "symbol": symbol,
                    "date": str(d.date()),
                    "contains_bar_of": other,
                    "cached_close": round(row_close, 4),
                    "real_close": round(own_close, 4),
                })
                break
    return findings


def detect_mosaic(
    cached: pd.DataFrame,
    fresh: pd.DataFrame,
    symbol: str,
) -> List[dict]:
    """(b) del spec: mosaico = bases de reajuste mezcladas DENTRO del
    archivo. Método del doc §4: ratio cache/fresco por día; un archivo sano
    es un plateau único (ratio constante, el jitter ±1bp de Yahoo se cancela
    en el ratio); un mosaico tiene >=2 plateaus (seam en la fecha donde la
    base cambia).

    Devuelve la lista de seams con el nivel del ratio a cada lado. Umbral:
    saltos > MOSAIC_RATIO_TOL entre medianas de tramos >= MOSAIC_MIN_SEGMENT
    días (el seam de AAPL medido: 1.00086 -> 1.0; el ruido ±1bp queda abajo
    de la tolerancia).
    """
    cached = _norm(cached)
    fresh = _norm(fresh)
    joined = pd.DataFrame({"cache": cached["close"], "fresh": fresh["close"]}).dropna()
    if len(joined) < 2 * MOSAIC_MIN_SEGMENT:
        return []
    joined = joined[(joined["fresh"].abs() > 0) & (joined["cache"].abs() > 0)]
    if len(joined) < 2 * MOSAIC_MIN_SEGMENT:
        return []
    ratio = joined["cache"] / joined["fresh"]
    seams = []
    n = len(ratio)
    # Un seam de mosaico es un SALTO de un día: el ratio cache/fresco salta del
    # nivel viejo al nuevo y se QUEDA (plateaus del doc §4). El paso por
    # ventanas deslizantes genera niveles fantasma (mediana de ventana que
    # cruza la frontera con 50% de cada base); el salto puntual no.
    # Criterio: |Δratio| en un día > MOSAIC_RATIO_TOL y las medianas de las
    # M ventanas a cada lado del salto difieren también (verificación con
    # ventanas PURAS — adyacentes al escalón, nunca cruzándolo).
    M = MOSAIC_MIN_SEGMENT
    steps = ratio.diff().abs()
    for i in range(1, n):
        if float(steps.iloc[i]) <= MOSAIC_RATIO_TOL:
            continue
        lo = max(0, i - M)
        s0, s1 = lo, i
        if s1 - s0 < M // 2:
            continue
        e1 = min(n, i + M)
        if e1 - i < M // 2:
            continue
        before = float(ratio.iloc[s0:s1].median())
        after = float(ratio.iloc[i:e1].median())
        if abs(after - before) > MOSAIC_RATIO_TOL:
            seams.append({
                "symbol": symbol,
                "seam": str(pd.Timestamp(ratio.index[i]).date()),
                "ratio_before": round(before, 6),
                "ratio_after": round(after, 6),
            })
    return seams


# --------------------------------------------------------------------------
# Reparación dirigida (los tres modos de re-descarga del spec)
# --------------------------------------------------------------------------


def repair_full_redownload(
    symbol: str,
    cache_path: str,
    downloader,
    start: str,
    end: str,
) -> Optional[pd.DataFrame]:
    """(a)/(b): BLOQUEO + re-descarga del archivo COMPLETO.

    Reemplaza el parquet entero con la descarga fresca. Usado cuando hay
    contaminación confirmada (fila de otro símbolo) o mosaico: el append
    parcial no puede reparar una base mezclada — hace falta re-bajar todo
    el rango en una sola base de reajuste.
    """
    fresh = downloader(symbol, start=start, end=end)
    if fresh is None or len(fresh) == 0:
        return None
    fresh = _norm(fresh)
    fresh.to_parquet(cache_path)
    return fresh


def repair_gap_range(
    symbol: str,
    cache_path: str,
    downloader,
    gap_days: List[str],
    pad_days: int = 7,
) -> Optional[pd.DataFrame]:
    """(c): re-descarga SOLO el tramo faltante (con padding de margen para
    que el dedup por índice del append sea seguro) y lo inserta.

    Difiere del refresh normal de data_ingestion en el punto exacto que el
    doc §3.4/§6 marca: pide el RANGO INTERMEDIO, no el extremo derecho. El
    padding rodea el hueco de fechas contiguas ya presentes para que la
    descarga cubra el tramo completo con su propia base de reajuste
    (reemplazamos las filas solapadas del tramo, no solo la falta).
    """
    if not gap_days:
        return None
    cached = _norm(pd.read_parquet(cache_path))
    wanted = sorted(pd.Timestamp(d) for d in gap_days)
    # tramos contiguos de huecos (días de mercado consecutivos o casi)
    spans: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    span_start = wanted[0]
    prev = wanted[0]
    for d in wanted[1:]:
        if (d - prev).days > 10:  # corte de tramo: hueco nuevo lejos del anterior
            spans.append((span_start, prev))
            span_start = d
        prev = d
    spans.append((span_start, prev))
    df = cached
    repaired = 0
    for s, e in spans:
        req_start = (s - pd.Timedelta(days=pad_days)).strftime("%Y-%m-%d")
        req_end = (e + pd.Timedelta(days=pad_days + 1)).strftime("%Y-%m-%d")
        chunk = downloader(symbol, start=req_start, end=req_end)
        if chunk is None or len(chunk) == 0:
            print(f"[cache_integrity] {symbol} gap repair {s.date()}..{e.date()}: "
                  "yfinance returned empty (posible cierre de mercado)")
            continue
        chunk = _norm(chunk)
        # reemplaza el tramo completo (hueco + solape): el chunk viene en
        # una sola base de reajuste; mezclarlo con filas viejas del mismo
        # tramo recrearía un mosaico local.
        df = pd.concat([df[~df.index.isin(chunk.index)], chunk]).sort_index()
        repaired += 1
    if repaired == 0:
        return None
    df.to_parquet(cache_path)
    still = find_intermediate_gaps(df)
    if still:
        print(f"[cache_integrity] {symbol} gap repair: quedan {len(still)} huecos "
              f"({still[0]}..{still[-1]}) — re-descarga devuelta incompleta")
    return df


# --------------------------------------------------------------------------
# Orquestación: el harness completo por símbolo
# --------------------------------------------------------------------------


def _market_days_present_in_cache(cache_dir: str, symbols: List[str]) -> set:
    """Fechas que AL MENOS UN símbolo del cache tiene (auto-corrección del
    calendario para cierres no programables: si el mercado entero cerró,
    ningún símbolo tiene la fecha y no es hueco de nadie)."""
    present = set()
    for sym in symbols:
        path = os.path.join(cache_dir, f"{sym}.parquet")
        if not os.path.exists(path):
            continue
        df = pd.read_parquet(path)
        for d in pd.DatetimeIndex(df.index):
            present.add(pd.Timestamp(d).date())
    return present


def reconcile_symbol(
    symbol: str,
    cache_dir: str,
    downloader,
    start: str = "2015-01-01",
    end: Optional[str] = None,
    other_symbols_fresh: Optional[Dict[str, pd.DataFrame]] = None,
    known_trading_days: Optional[set] = None,
) -> dict:
    """Harness completo para UN símbolo: sanidad + reconciliación + reparación.

    `downloader(ticker, start=..., end=...)` es yf.download (o el mock del
    test). Orden:
      1. flags de retorno (parte 1) sobre el cache actual;
      2. descarga fresca del símbolo y comparación:
         (a) contaminación cruzada confirmada -> re-descarga COMPLETA;
         (b) mosaico -> re-descarga COMPLETA;
         (c) huecos intermedios -> re-descarga del tramo;
      3. re-valida después de reparar y reporta el estado final.

    Devuelve un reporte dict con todo lo encontrado/reparado para el log
    del updater. `other_symbols_fresh` permite reusar descargas frescas ya
    hechas (el harness completo de 102 pasa 1 vez por símbolo y acumula).
    """
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    cache_path = os.path.join(cache_dir, f"{symbol}.parquet")
    report: dict = {
        "symbol": symbol,
        "flags_returns": [],
        "contamination": [],
        "mosaic": [],
        "gaps": [],
        "actions": [],
        "final_flags": [],
    }
    if not os.path.exists(cache_path):
        report["actions"].append("sin cache: nada que reconciliar (download_data lo crea)")
        return report
    cached = _norm(pd.read_parquet(cache_path))

    # 1) sanidad de retornos sobre lo que hay en disco
    report["flags_returns"] = validate_returns(cached, symbol)

    # 2) fresco del propio símbolo (la referencia de la comparación)
    fresh = downloader(symbol, start=start, end=end)
    if fresh is None or len(fresh) == 0:
        report["actions"].append("descarga fresca vacía: no se reconcilia hoy (log explícito)")
        return report
    fresh = _norm(fresh)

    # 2a) contaminación cruzada — confirmación con OHLCV de otro símbolo
    #     (criterio §3.1) cuando hay descargas frescas de los demás; si no
    #     las hay, el hard-flag + divergencia vs fresco propio alcanza para
    #     disparar la re-descarga completa (ticket A0 Verificación #1:
    #     "detectada y dispara re-descarga"): una barra que diverge de su
    #     propia descarga fresca en >PRICE_TOL con hard-flag de retorno es
    #     basura congelada, venga de otro símbolo o de un bad tick.
    contamination = detect_cross_contamination(
        cached, fresh, other_symbols_fresh or {}, symbol,
    )
    report["contamination"] = contamination

    # 2b) mosaico
    mosaic = detect_mosaic(cached, fresh, symbol)
    report["mosaic"] = mosaic

    # divergencia vs fresco propio en los días con hard-flag
    divergent_hard = []
    for f in report["flags_returns"]:
        if f["level"] != "hard":
            continue
        own = _row_from(fresh, f["date"])
        if own is None:
            continue
        cache_row = _row_from(cached, f["date"])
        if cache_row is None:
            continue
        c_close, f_close = float(cache_row["close"]), float(own["close"])
        if abs(c_close - f_close) / abs(f_close) > PRICE_TOL:
            divergent_hard.append(f["date"])

    if contamination or mosaic or divergent_hard:
        motivos = []
        if contamination:
            motivos.append(f"contaminacion ({len(contamination)} barras, ej. "
                           f"{contamination[0]['date']} = barra de {contamination[0]['contains_bar_of']})")
        if mosaic:
            motivos.append(f"mosaico ({len(mosaic)} seams, ej. {mosaic[0]['seam']}: "
                           f"{mosaic[0]['ratio_before']} -> {mosaic[0]['ratio_after']})")
        if divergent_hard and not contamination:
            motivos.append(f"hard-flag divergente vs fresco ({len(divergent_hard)} barras, ej. {divergent_hard[0]})")
        print(f"[cache_integrity] {symbol} BLOQUEO: {'; '.join(motivos)} -> re-descarga completa")
        repaired = repair_full_redownload(symbol, cache_path, downloader, start, end)
        if repaired is not None:
            report["actions"].append("re-descarga completa (contaminacion/mosaico)")
            cached = repaired
        else:
            report["actions"].append("re-descarga completa FALLO (yfinance vacío) — queda BLOQUEADO")
            return report
    # 2c) huecos intermedios
    gaps = find_intermediate_gaps(cached, known_trading_days)
    report["gaps"] = gaps
    if gaps:
        print(f"[cache_integrity] {symbol} huecos intermedios: {len(gaps)} "
              f"({gaps[0]}..{gaps[-1]}) -> re-descarga del tramo")
        repaired = repair_gap_range(symbol, cache_path, downloader, gaps)
        if repaired is not None:
            report["actions"].append(f"re-descarga tramo ({len(gaps)} huecos)")
            cached = repaired
        else:
            report["actions"].append("reparación de tramo sin efecto (yfinance vacío)")

    # 3) estado final
    report["final_flags"] = validate_returns(cached, symbol)
    report["final_gaps"] = find_intermediate_gaps(cached, known_trading_days)
    return report


def reconcile_cache(
    cache_dir: str,
    downloader,
    symbols: Optional[List[str]] = None,
    start: str = "2015-01-01",
    end: Optional[str] = None,
) -> List[dict]:
    """Harness completo sobre el universo (los 102 reales por defecto).

    Pasa 1 vez por símbolo, acumula las descargas frescas para el
    cross-check de contaminación (una barra contaminada matchea la barra
    REAL del otro símbolo: con las descargas frescas de todos los símbolos
    alcanza para confirmar cualquier par), y devuelve la lista completa de
    reportes para el log/artefacto de la corrida.
    """
    symbols = symbols if symbols is not None else _universe_symbols()
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    known = _market_days_present_in_cache(cache_dir, symbols)
    fresh_by_symbol: Dict[str, pd.DataFrame] = {}
    reports = []
    for symbol in symbols:
        fresh = downloader(symbol, start=start, end=end)
        if fresh is not None and len(fresh):
            fresh_by_symbol[symbol] = _norm(fresh)
        reports.append(reconcile_symbol(
            symbol, cache_dir, downloader, start, end,
            other_symbols_fresh=fresh_by_symbol,
            known_trading_days=known,
        ))
    return reports


# --------------------------------------------------------------------------
# Parte 3 — Snapshot/hash del cache por trial
# --------------------------------------------------------------------------


def _canonical_bytes(df: pd.DataFrame) -> bytes:
    """Serialización canónica para hashing: índice fecha ISO + columnas
    OHLCV ordenadas, floats en formato estable. Dos corridas del mismo
    contenido dan el mismo hash aunque el parquet se re-escriba."""
    d = _norm(df)[["open", "high", "low", "close", "volume"]].dropna(how="all")
    lines = []
    for day, row in d.iterrows():
        vals = ",".join(f"{float(row[c]):.6f}" for c in ("open", "high", "low", "close", "volume"))
        lines.append(f"{pd.Timestamp(day).date().isoformat()}|{vals}")
    return "\n".join(lines).encode("utf-8")


def snapshot_hash(cache_dir: str, symbols: Optional[List[str]] = None) -> dict:
    """Manifiesto {archivo: {filas, rango, sha256}} del cache del universo.

    El pre-registro de cada trial debe congelar ESTO (o una copia congelada
    de los parquets): es la única defensa contra el reajuste retroactivo de
    Yahoo (doc §2: cada dividendo nuevo re-escribe el pasado completo — un
    backtest corrido hoy y hace 6 meses usa bases distintas aunque el código
    sea idéntico). Con el hash, un re-run posterior verifica si el cache que
    consume sigue siendo bit-el-mismo-contenido que el del veredicto.
    """
    symbols = symbols if symbols is not None else _universe_symbols()
    manifest: Dict[str, dict] = {}
    for symbol in symbols:
        path = os.path.join(cache_dir, f"{symbol}.parquet")
        if not os.path.exists(path):
            manifest[symbol] = {"missing": True}
            continue
        df = pd.read_parquet(path)
        digest = hashlib.sha256(_canonical_bytes(df)).hexdigest()
        manifest[symbol] = {
            "rows": int(len(df)),
            "range": [str(pd.Timestamp(df.index[0]).date()),
                      str(pd.Timestamp(df.index[-1]).date())],
            "sha256": digest,
        }
    return manifest


def cache_snapshot_for_trial(
    cache_dir: str,
    trial_id: str,
    symbols: Optional[List[str]] = None,
    out_dir: Optional[str] = None,
) -> dict:
    """Snapshot listo para adjuntar al pre-registro de un trial.

    Escribe data/cache_snapshots/<trial_id>.json (ruta por defecto) con:
      - ts de la corrida, universo, rango global;
      - hash por símbolo (snapshot_hash);
      - resumen del estado de integridad (flags/gaps) del momento.
    `out_dir` permite el directorio del trial (copias congeladas).
    """
    symbols = symbols if symbols is not None else _universe_symbols()
    manifest = snapshot_hash(cache_dir, symbols)
    known = _market_days_present_in_cache(cache_dir, symbols)
    integrity = {}
    for symbol in symbols:
        path = os.path.join(cache_dir, f"{symbol}.parquet")
        if not os.path.exists(path):
            continue
        df = _norm(pd.read_parquet(path))
        flags = validate_returns(df, symbol)
        gaps = find_intermediate_gaps(df, known)
        if flags or gaps:
            integrity[symbol] = {"flags": len(flags), "gaps": gaps}
    firsts = [m["range"][0] for m in manifest.values() if "range" in m]
    lasts = [m["range"][1] for m in manifest.values() if "range" in m]
    payload = {
        "trial_id": trial_id,
        "generated": pd.Timestamp.now().isoformat(),
        "n_symbols": len(symbols),
        "cache_range": [min(firsts), max(lasts)] if firsts and lasts else None,
        "symbols": manifest,
        "integrity_warnings": integrity,
    }
    if out_dir is None:
        out_dir = os.path.join(cache_dir, "..", "cache_snapshots")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{trial_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    payload["snapshot_path"] = path
    return payload


def attach_cache_snapshot(
    entry: dict,
    cache_dir: str,
    out_dir: Optional[str] = None,
) -> dict:
    """Congela el snapshot del cache en la entrada de un pre-registro.

    Uso (el caller es register_trial / register_trial_reservation):

        entry = attach_cache_snapshot(entry, cache_dir)
        register_trial_reservation(entry, ...)

    La entrada queda con `cache_snapshot` (ruta al JSON) y
    `cache_manifest_sha256` (hash del manifiesto completo — verificación de
    un solo número en auditoría). Ruidoso si la entrada no tiene id de trial.
    """
    trial_id = entry.get("id") or ""
    if not str(trial_id).strip():
        raise ValueError("attach_cache_snapshot exige entrada con 'id' (trial del ledger)")
    snap = cache_snapshot_for_trial(cache_dir, trial_id, out_dir=out_dir)
    manifest_json = json.dumps(
        {k: v for k, v in snap.items() if k != "snapshot_path"},
        sort_keys=True,
    ).encode("utf-8")
    entry = dict(entry)
    entry["cache_snapshot"] = snap["snapshot_path"]
    entry["cache_manifest_sha256"] = hashlib.sha256(manifest_json).hexdigest()
    return entry
