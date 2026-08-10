"""
Datos de sentimiento del mercado y liquidez (Fase E.1 v3 — variables V2/V3).

Fuentes (100% públicas, sin API key — verificadas el 2026-08-09):
- FRED via fredgraph.csv (endpoint público sin key): WALCL (activos Fed,
  semanal), RRPONTSYD (reverse repo, diario), WRESBAL (reservas, semanal).
- CFTC Financial COT (com_fin_txt_YYYY.zip -> FinComYY.txt): posicionamiento
  semanal del E-MINI S&P 500 por tipo de trader (Dealer, Asset_Mgr,
  Lev_Money/hedge funds, Other_Rept, NonRept/retail).
- AAII (sentiment.xls, verificado 2026-08-09): encuesta semanal del sentimiento
  inversor minorista (Bullish/Neutral/Bearish) desde 1987. Fuente principal de
  V1: mide la ACTITUD de la gente, no posiciones (a diferencia del COT).
  - NAAIM (exposure index): movió a suscripción paga (2025+) -> descartado.
  - CBOE put/call: CDN diario 2019+ bloquea bots (403 AccessDenied); los CSVs
    estáticos oficiales solo llegan a 10/2019 -> pendiente de fuente gratuita.

Disciplina anti-lookahead (obligatoria):
- COT se publica viernes tras el cierre; FRED semanal se publica miércoles;
  AAII se publica jueves tras el cierre.
- Por eso el valor del día t se construye con shift(1) + forward-fill: solo
  usa información publicada ANTES de t. Sin esto, el IC miente.
"""
import os
import time
import zipfile
import io

import requests
import pandas as pd
import numpy as np

CACHE_DIR = "data/cache"

# AAII publica los jueves: el cache parquet expira a la semana. Con esto el
# path en vivo descarga el xls como MÁXIMO una vez por semana (nunca por
# request), y si la descarga falla se degrada al cache stale en vez de perder
# el dato (ver fetch_aaii).
AAII_CACHE_MAX_AGE_DAYS = 7

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


def _get(url: str, timeout: int = 60, retries: int = 3) -> requests.Response:
    """GET con reintentos y doble transporte.

    - requests/urllib3 primero: funciona contra CFTC.
    - Si falla el handshake TLS (venv con LibreSSL, e.g. FRED), reintenta con
      curl_cffi impersonando Chrome.
    """
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        cffi_requests = None

    def _plain():
        return requests.get(url, headers=_HEADERS, timeout=timeout)

    def _cffi():
        return cffi_requests.get(url, impersonate="chrome", timeout=timeout)

    last_err = None
    for attempt in range(retries):
        try:
            resp = _plain()
            if resp.status_code == 403 and cffi_requests is not None:
                # CFTC/FRED bloquean el fingerprint TLS de urllib3: probar
                # curl_cffi (impersona Chrome) antes de darse por vencido.
                resp = _cffi()
            return resp
        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(2 * (attempt + 1))

    if cffi_requests is not None:
        try:
            return _cffi()
        except Exception as e:
            last_err = e

    raise last_err

FRED_SERIES = {
    "WALCL": "assets Fed semanal (millones USD)",
    "RRPONTSYD": "reverse repo ON diario (millones USD)",
    "WRESBAL": "reservas bancarias semanal (millones USD)",
}

COT_URL = "https://www.cftc.gov/files/dea/history/com_fin_txt_{year}.zip"
COT_MARKET = "E-MINI S&P 500"
COT_START_YEAR = 2019

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

AAII_URL = "https://www.aaii.com/files/surveys/sentiment.xls"


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


def fetch_fred(series: str) -> pd.Series:
    """Serie FRED con cache parquet. Fecha del dato = fecha de publicación
    (para WALCL/WRESBAL: miércoles de cierre de semana; RRP: día hábil)."""
    cache = _cache_path(f"fred_{series}.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)["value"]
    resp = _get(FRED_URL.format(series=series), timeout=60)
    resp.raise_for_status()
    raw = resp.text
    df = pd.read_csv(io.StringIO(raw))
    df.columns = [c.strip() for c in df.columns]
    df["date"] = pd.to_datetime(df["observation_date"])
    df["value"] = pd.to_numeric(df[series], errors="coerce")
    out = df.set_index("date")["value"].dropna().sort_index()
    os.makedirs(CACHE_DIR, exist_ok=True)
    out.to_frame("value").to_parquet(cache)
    return out


def fetch_cot_years(years: list) -> pd.DataFrame:
    """Posiciones semanales del E-MINI S&P 500 (Financial COT) por tipo de trader.

    Retorna DataFrame indexado por fecha de reporte con columnas:
      cot_lev_net, cot_asset_net, cot_retail_net  (contratos netos long-short)
      cot_oi                                     (open interest total)
    """
    frames = []
    for year in years:
        cache = _cache_path(f"cot_{year}.parquet")
        if os.path.exists(cache):
            frames.append(pd.read_parquet(cache))
            continue
        url = COT_URL.format(year=year)
        try:
            resp = _get(url, timeout=120)
            if resp.status_code == 403:
                print(f"  COT {year}: 403 Forbidden, se salta")
                continue
            resp.raise_for_status()
            zdata = zipfile.ZipFile(io.BytesIO(resp.content))
        except Exception as e:
            print(f"  COT {year}: no accesible ({e}), se salta")
            continue
        fname = [n for n in zdata.namelist() if n.endswith(".txt")]
        if not fname:
            continue
        with zdata.open(fname[0]) as f:
            df = pd.read_csv(f)
        df.columns = [c.strip() for c in df.columns]
        market = df[df["Market_and_Exchange_Names"].str.strip().str.startswith(COT_MARKET)].copy()
        if market.empty:
            print(f"  COT {year}: sin mercado {COT_MARKET!r}, se salta")
            continue
        market["date"] = pd.to_datetime(market["Report_Date_as_YYYY-MM-DD"])
        market = market.sort_values("date").drop_duplicates("date", keep="last")
        # .to_numpy(): evita que pandas alinee por label (índice 0..n del CSV
        # vs DatetimeIndex de salida), que silenciosamente produce todo NaN.
        out = pd.DataFrame(
            {
                "cot_oi": pd.to_numeric(market["Open_Interest_All"], errors="coerce").to_numpy(),
                "cot_lev_net": (
                    pd.to_numeric(market["Lev_Money_Positions_Long_All"], errors="coerce").to_numpy()
                    - pd.to_numeric(market["Lev_Money_Positions_Short_All"], errors="coerce").to_numpy()
                ),
                "cot_asset_net": (
                    pd.to_numeric(market["Asset_Mgr_Positions_Long_All"], errors="coerce").to_numpy()
                    - pd.to_numeric(market["Asset_Mgr_Positions_Short_All"], errors="coerce").to_numpy()
                ),
                "cot_retail_net": (
                    pd.to_numeric(market["NonRept_Positions_Long_All"], errors="coerce").to_numpy()
                    - pd.to_numeric(market["NonRept_Positions_Short_All"], errors="coerce").to_numpy()
                ),
                "cot_dealer_net": (
                    pd.to_numeric(market["Dealer_Positions_Long_All"], errors="coerce").to_numpy()
                    - pd.to_numeric(market["Dealer_Positions_Short_All"], errors="coerce").to_numpy()
                ),
            },
            index=pd.DatetimeIndex(market["date"]),
        )
        os.makedirs(CACHE_DIR, exist_ok=True)
        out.to_parquet(cache)
        frames.append(out)
    if not frames:
        raise RuntimeError("Sin datos COT para ningún año")
    combined = pd.concat(frames).sort_index()
    return combined.loc[~combined.index.duplicated(keep="last")]


def _aaii_cache_path() -> str:
    return _cache_path("aaii_spread.parquet")


def _aaii_cache_age_days(path: str) -> float:
    """Edad del cache en días (mtime). Infinito si no existe."""
    try:
        return (time.time() - os.path.getmtime(path)) / 86400.0
    except OSError:
        return float("inf")


def _read_aaii_cache(path: str) -> pd.Series:
    return pd.read_parquet(path)["value"]


def fetch_aaii() -> pd.Series:
    """Bull-Bear spread de la encuesta AAII (publicación jueves tras el cierre).

    El xls tiene headers en la fila 3 (Date/Bullish/Neutral/Bearish/Total/
    Mov Avg/Spread/Average), datos desde la fila 5 y una fila de resumen
    final ('Count YY') que hay que descartar. Bullish/Bearish vienen en
    fracción 0-1 -> se pasan a porcentaje. Retorna el spread (Bull-Bear)
    en puntos porcentuales, indexado por fecha de publicación.

    Cache: parquet con TTL semanal (AAII publica los jueves). Si la descarga
    falla y existe cache, devuelve el cache stale (dato viejo > nada) en vez
    de propagar el error — el request en vivo degrada a baseline igual.
    """
    cache = _aaii_cache_path()
    if os.path.exists(cache) and _aaii_cache_age_days(cache) < AAII_CACHE_MAX_AGE_DAYS:
        return _read_aaii_cache(cache)

    # Cache viejo (o inexistente): intentar refrescar. Si falla y hay cache,
    # devolver el stale (dato viejo > nada) — el request en vivo nunca se cae.
    try:
        resp = _get(AAII_URL, timeout=90)
        resp.raise_for_status()
        raw = pd.read_excel(io.BytesIO(resp.content), header=None)
        hdr = raw.iloc[3].to_list()[:8]
        data = raw.iloc[5:].copy()
        data.columns = ["Date", "Bullish", "Neutral", "Bearish", "Total", "Mov Avg", "Spread", "Average"] + [
            f"x{i}" for i in range(len(data.columns) - 8)
        ]
        data = data[pd.to_datetime(data["Date"], errors="coerce").notna()].copy()
        data["Date"] = pd.to_datetime(data["Date"])
        spread = (pd.to_numeric(data["Bullish"], errors="coerce") - pd.to_numeric(data["Bearish"], errors="coerce")) * 100
        out = pd.Series(spread.to_numpy(), index=pd.DatetimeIndex(data["Date"])).dropna().sort_index()
        if len(out) < 400:
            # El xls cambió de formato (la serie completa arranca en 1987, ~2000+ semanas).
            # No sobreescribir un cache bueno con basura — tirar el dato.
            raise RuntimeError(f"AAII xls con formato inesperado: {len(out)} filas (< 400)")
        os.makedirs(CACHE_DIR, exist_ok=True)
        out.to_frame("value").to_parquet(cache)
        return out
    except Exception:
        if os.path.exists(cache):
            # Degradar al cache stale: mejor dato viejo que sin dato.
            return _read_aaii_cache(cache)
        raise


def build_sentiment_frame(trading_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Panel diario de sentimiento/liquidez alineado a fechas de trading.

    Alineación anti-lookahead: cada fuente se reindexa a las fechas de trading
    con shift(1) (el dato se publicó el día anterior o antes) + forward-fill.

    Columnas:
      walcl_level, walcl_growth_w   (WALCL y su cambio semanal %)
      rrponsytd_level               (reverse repo diario)
      wresbal_level, wresbal_growth_w
      aaii_bullbear_spread          (AAII Bull-Bear en puntos %, semanal)
      cot_lev_net_pct, cot_asset_net_pct, cot_retail_net_pct, cot_dealer_net_pct
        (netos como % del open interest — comparables a través del tiempo)
    """
    trading = pd.Series(1.0, index=trading_dates.sort_values())

    walcl = fetch_fred("WALCL")
    rrpon = fetch_fred("RRPONTSYD")
    wresbal = fetch_fred("WRESBAL")
    cot = fetch_cot_years(list(range(COT_START_YEAR, 2027)))
    aaii = fetch_aaii()

    def _align(series: pd.Series, name: str) -> pd.Series:
        joined = pd.concat([series, trading], axis=1).sort_index().iloc[:, 0]
        return joined.shift(1).ffill().reindex(trading_dates)

    def _growth(level: pd.Series, weeks: int = 4) -> pd.Series:
        """Cambio % contra `weeks` observaciones atrás (semanal aprox.)."""
        return level.pct_change(periods=weeks)

    out = pd.DataFrame(index=trading_dates)
    out["walcl_level"] = _align(walcl, "walcl")
    out["walcl_growth_w"] = _growth(out["walcl_level"])
    out["rrponsytd_level"] = _align(rrpon, "rrpon")
    out["wresbal_level"] = _align(wresbal, "wresbal")
    out["wresbal_growth_w"] = _growth(out["wresbal_level"])
    out["aaii_bullbear_spread"] = _align(aaii, "aaii")

    cot_pct = pd.DataFrame(index=cot.index)
    for col in ["cot_lev_net", "cot_asset_net", "cot_retail_net", "cot_dealer_net"]:
        cot_pct[f"{col}_pct"] = (cot[col] / cot["cot_oi"].replace(0, np.nan)) * 100
    for col in cot_pct.columns:
        out[col] = _align(cot_pct[col], col)

    return out


if __name__ == "__main__":
    idx = pd.date_range("2019-01-01", "2024-12-31", freq="B")
    frame = build_sentiment_frame(idx)
    print(frame.tail(5).to_string())
