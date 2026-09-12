"""Institutional Fingerprint — Phase 2 of institutional-flow-score.

Fetches COT, AAII, FRED data and computes 9 causal z-score variables + regime
fingerprint statistics. All computations strictly causal (data ≤ as_of only).

Variables (9):
1. cot_asset_mgr_z        — z-score 252d expanding (Asset Mgr net % OI)
2. cot_lev_money_z        — z-score 252d expanding (Lev Money net % OI)
3. aaii_spread_z          — z-score 252d expanding (AAII Bull-Bear spread)
4. fg_score               — raw 0-100 Fear & Greed (shift 1)
5. put_call_ratio         — raw Put/Call ratio (shift 1)
6. vix_pctl_1y            — percentileofscore(VIX 252d, VIX today)
7. phase_b_quiet          — binary: vol_b < vol_a (20d window)
8. retest_confirmed       — binary: A→B→C retest pattern detected
"""

import io
import os
import time
import zipfile
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr

CACHE_DIR = "data/cache"

# AAII publica los jueves: cache parquet expira a la semana
AAII_CACHE_MAX_AGE_DAYS = 7

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

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

# Fear & Greed components URLs (CNNMoney)
FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
PUT_CALL_URL = "https://www.cboe.com/us/options/market_statistics/daily/"


def _get(url: str, timeout: int = 60, retries: int = 3) -> requests.Response:
    """GET con reintentos y doble transporte (requests + curl_cffi fallback).

    - requests/urllib3 primero: funciona contra CFTC.
    - Si falla el handshake TLS (venv con LibreSSL, e.g. FRED), reintenta con
      curl_cffi impersonando Chrome.
    - 403 handling pattern from market_sentiment.py
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


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


# ============================================================================
# FRED FETCHER (reuses market_sentiment.py pattern)
# ============================================================================

def fetch_fred(series: str) -> pd.Series:
    """Serie FRED con cache parquet. Fecha del dato = fecha de publicación."""
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


# ============================================================================
# COT FETCHER (TASK-005)
# ============================================================================

def fetch_cot_years(years: List[int]) -> pd.DataFrame:
    """Posiciones semanales del E-MINI S&P 500 (Financial COT) por tipo de trader.

    Retorna DataFrame indexado por fecha de reporte con columnas:
      cot_asset_net, cot_lev_net, cot_retail_net, cot_dealer_net, cot_oi
    Cache: data/cache/cot_YYYY.parquet por año.
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


# ============================================================================
# AAII FETCHER (TASK-006 - reuses market_sentiment.py pattern exactly)
# ============================================================================

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

    Cache: parquet con TTL semanal. Si la descarga falla y existe cache,
    devuelve el cache stale (dato viejo > nada).
    """
    cache = _aaii_cache_path()
    if os.path.exists(cache) and _aaii_cache_age_days(cache) < AAII_CACHE_MAX_AGE_DAYS:
        return _read_aaii_cache(cache)

    try:
        resp = _get(AAII_URL, timeout=90)
        resp.raise_for_status()
        raw = pd.read_excel(io.BytesIO(resp.content), header=None)
        _hdr = raw.iloc[3].to_list()[:8]
        data = raw.iloc[5:].copy()
        data.columns = ["Date", "Bullish", "Neutral", "Bearish", "Total", "Mov Avg", "Spread", "Average"] + [
            f"x{i}" for i in range(len(data.columns) - 8)
        ]
        data = data[pd.to_datetime(data["Date"], errors="coerce").notna()].copy()
        data["Date"] = pd.to_datetime(data["Date"])
        spread = (pd.to_numeric(data["Bullish"], errors="coerce") - pd.to_numeric(data["Bearish"], errors="coerce")) * 100
        out = pd.Series(spread.to_numpy(), index=pd.DatetimeIndex(data["Date"])).dropna().sort_index()
        if len(out) < 400:
            raise RuntimeError(f"AAII xls con formato inesperado: {len(out)} filas (< 400)")
        os.makedirs(CACHE_DIR, exist_ok=True)
        out.to_frame("value").to_parquet(cache)
        return out
    except Exception:
        if os.path.exists(cache):
            return _read_aaii_cache(cache)
        raise


# ============================================================================
# FEAR & GREED + PUT/CALL FETCHERS
# ============================================================================

def fetch_fear_greed() -> pd.Series:
    """CNN Fear & Greed Index (0-100). Daily.

    Cache: data/cache/fg_score.parquet
    """
    cache = _cache_path("fg_score.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)["value"]

    try:
        resp = _get(FG_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # CNN FG returns {"fear_and_greed": {"score": x, "rating": "..."}, "timestamp": "..."}
        # The graphdata endpoint returns historical data
        scores = []
        dates = []
        if "data" in data:
            for entry in data["data"]:
                if "x" in entry and "y" in entry:
                    dates.append(pd.Timestamp(entry["x"], unit="ms"))
                    scores.append(float(entry["y"]))
        if scores:
            out = pd.Series(scores, index=pd.DatetimeIndex(dates)).sort_index()
            os.makedirs(CACHE_DIR, exist_ok=True)
            out.to_frame("value").to_parquet(cache)
            return out
    except Exception:
        pass

    # Return empty series if failed
    return pd.Series(dtype=float)


def fetch_put_call_ratio() -> pd.Series:
    """CBOE Put/Call Ratio. Daily.

    Cache: data/cache/put_call_ratio.parquet
    Note: CBOE blocks bots, may need fallback. For now return empty if blocked.
    """
    cache = _cache_path("put_call_ratio.parquet")
    if os.path.exists(cache):
        return pd.read_parquet(cache)["value"]

    # CBOE CSVs are behind CDN that blocks bots
    # Try to fetch but expect 403
    try:
        _ = _get(PUT_CALL_URL, timeout=30)
        # If we get here, parse HTML for the ratio table
        # For now, return empty - real implementation would parse HTML
        pass
    except Exception:
        pass

    return pd.Series(dtype=float)


# ============================================================================
# VIX FETCHER (from local cache)
# ============================================================================

def fetch_vix() -> pd.Series:
    """VIX index from local parquet cache (^VIX.parquet)."""
    cache = _cache_path("^VIX.parquet")
    if os.path.exists(cache):
        df = pd.read_parquet(cache)
        if "close" in df.columns:
            return df["close"].dropna().sort_index()
    return pd.Series(dtype=float)


# ============================================================================
# PRICE STRUCTURE / THERMOMETER (for phase_b_quiet and retest)
# ============================================================================

def _compute_volatility(close: pd.Series, window: int = 20) -> pd.Series:
    """Rolling realized volatility (std of log returns * sqrt(252))."""
    log_ret = np.log(close / close.shift(1))
    vol = log_ret.rolling(window).std() * np.sqrt(252)
    return vol


def build_thermometer_frame(spy_close: pd.Series) -> pd.DataFrame:
    """Build price structure frame for SPY with vol_a, vol_b, retest detection.

    Price structure logic (A→B→C pattern):
    - Phase A: Initial move (vol_a = vol over first 10d of 20d window)
    - Phase B: Consolidation (vol_b = vol over last 10d of 20d window)
    - Phase C: Retest/breakout

    Returns DataFrame with:
    - vol_a: volatility first half of 20d window
    - vol_b: volatility second half of 20d window
    - phase_b_quiet: binary (vol_b < vol_a)
    - retest_confirmed: binary (A→B→C pattern detected)
    """
    # Full window volatility (20d)
    # vol_full = _compute_volatility(spy_close, window=20)

    # Split into two 10d halves within the 20d window
    # vol_a: volatility of days t-20 to t-10
    # vol_b: volatility of days t-10 to t
    log_ret = np.log(spy_close / spy_close.shift(1))

    # Rolling vol for first half (days -20 to -11)
    vol_a = log_ret.rolling(10).std().shift(10) * np.sqrt(252)
    # Rolling vol for second half (days -10 to -1)
    vol_b = log_ret.rolling(10).std() * np.sqrt(252)

    # Phase B quiet: consolidation (vol_b < vol_a)
    phase_b_quiet = (vol_b < vol_a).astype(int)

    # Retest pattern A→B→C:
    # A: directional move (|return| > 1.5 * vol_a over 10d)
    # B: consolidation (phase_b_quiet == 1)
    # C: retest of A extreme (price returns to A level within 5d)
    ret_10d = spy_close / spy_close.shift(10) - 1
    move_a = ret_10d.shift(10)  # Return over first 10d
    move_a_magnitude = move_a.abs()
    threshold_a = 1.5 * vol_a

    # Phase A: significant directional move
    phase_a = (move_a_magnitude > threshold_a).astype(int)

    # Phase B: quiet consolidation (already computed)
    phase_b = phase_b_quiet

    # Phase C: retest - price returns to within 0.5% of A extreme within 5 days
    # A extreme level = price at t-20 (start of move)
    # Check if price in t-5 to t touches that level
    price_a_extreme = spy_close.shift(20)

    # Check each of last 5 days
    retest_touch = pd.Series(False, index=spy_close.index)
    for i in range(1, 6):
        price_i = spy_close.shift(i)
        # Touch within 0.5%
        touch = (price_i / price_a_extreme - 1).abs() < 0.005
        retest_touch = retest_touch | touch

    # Retest confirmed: A and B happened, then C (retest touch)
    # Use fillna(False) for shifted boolean series to handle NaN from shift
    phase_a_shifted = phase_a.shift(10).fillna(0).astype(bool)
    phase_b_shifted = phase_b.shift(5).fillna(0).astype(bool)
    retest_confirmed = (phase_a_shifted & phase_b_shifted & retest_touch).astype(int)

    out = pd.DataFrame({
        "vol_a": vol_a,
        "vol_b": vol_b,
        "phase_b_quiet": phase_b_quiet,
        "retest_confirmed": retest_confirmed,
    }, index=spy_close.index)

    return out


# ============================================================================
# ALIGNMENT HELPER (causal: shift(1) + ffill)
# ============================================================================

def _align_causal(series: pd.Series, trading_dates: pd.DatetimeIndex, name: str) -> pd.Series:
    """Alineación anti-lookahead: shift(1) + ffill → reindex a trading_dates.

    El dato del día t se construye con información publicada ANTES de t.
    """
    joined = pd.concat([series, pd.Series(1.0, index=trading_dates)], axis=1).sort_index().iloc[:, 0]
    aligned = joined.shift(1).ffill().reindex(trading_dates)
    aligned.name = name
    return aligned


# ============================================================================
# Z-SCORE COMPUTATION (TASK-007)
# ============================================================================

ZSCORE_LOOKBACK = 252  # expanding window


def compute_zscores(regime_series: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """Compute 9 causal z-score variables as of a specific date.

    CRITICAL: Uses ONLY data ≤ as_of (strict causality).

    Args:
        regime_series: RegimeNowcaster regime probabilities/index (for alignment)
        as_of: Cutoff date — NO data after this date is used

    Returns:
        Series with 9 variables:
        1. cot_asset_mgr_z
        2. cot_lev_money_z
        3. aaii_spread_z
        4. fg_score (raw, shift 1)
        5. put_call_ratio (raw, shift 1)
        6. vix_pctl_1y
        7. phase_b_quiet
        8. retest_confirmed
        9. regime (current regime label as categorical)
    """
    # Trading dates up to as_of (inclusive)
    trading_dates = regime_series.index[regime_series.index <= as_of]
    if len(trading_dates) < ZSCORE_LOOKBACK:
        raise ValueError(f"Insufficient data: {len(trading_dates)} < {ZSCORE_LOOKBACK} required")

    # -----------------------------------------------------------------------
    # Fetch all raw data (cached, so fast)
    # -----------------------------------------------------------------------
    cot = fetch_cot_years(list(range(COT_START_YEAR, as_of.year + 2)))
    aaii = fetch_aaii()
    fg = fetch_fear_greed()
    pc = fetch_put_call_ratio()
    vix = fetch_vix()

    # Truncate ALL data to as_of (causal!)
    cot = cot[cot.index <= as_of]
    aaii = aaii[aaii.index <= as_of]
    fg = fg[fg.index <= as_of] if len(fg) > 0 else fg
    pc = pc[pc.index <= as_of] if len(pc) > 0 else pc
    vix = vix[vix.index <= as_of] if len(vix) > 0 else vix

    # SPY close for thermometer (from cache)
    spy_cache = _cache_path("SPY.parquet")
    if os.path.exists(spy_cache):
        spy_df = pd.read_parquet(spy_cache)
        spy_close = spy_df["close"].dropna().sort_index()
        spy_close = spy_close[spy_close.index <= as_of]
    else:
        spy_close = pd.Series(dtype=float)

    # -----------------------------------------------------------------------
    # Align all to trading dates with causal shift(1) + ffill
    # -----------------------------------------------------------------------

    # COT: net as % of OI
    cot_pct = pd.DataFrame(index=cot.index)
    for col in ["cot_lev_net", "cot_asset_net", "cot_retail_net", "cot_dealer_net"]:
        cot_pct[f"{col}_pct"] = (cot[col] / cot["cot_oi"].replace(0, np.nan)) * 100

    aligned = pd.DataFrame(index=trading_dates)

    # 1. cot_asset_mgr_z
    asset_aligned = _align_causal(cot_pct["cot_asset_net_pct"], trading_dates, "cot_asset_mgr")
    aligned["cot_asset_mgr_z"] = _expanding_zscore(asset_aligned, lookback=ZSCORE_LOOKBACK)

    # 2. cot_lev_money_z
    lev_aligned = _align_causal(cot_pct["cot_lev_net_pct"], trading_dates, "cot_lev_money")
    aligned["cot_lev_money_z"] = _expanding_zscore(lev_aligned, lookback=ZSCORE_LOOKBACK)

    # 3. aaii_spread_z
    aaii_aligned = _align_causal(aaii, trading_dates, "aaii_spread")
    aligned["aaii_spread_z"] = _expanding_zscore(aaii_aligned, lookback=ZSCORE_LOOKBACK)

    # 4. fg_score (raw, shift 1 already applied by _align_causal)
    if len(fg) > 0:
        aligned["fg_score"] = _align_causal(fg, trading_dates, "fg_score")
    else:
        aligned["fg_score"] = np.nan

    # 5. put_call_ratio (raw, shift 1)
    if len(pc) > 0:
        aligned["put_call_ratio"] = _align_causal(pc, trading_dates, "put_call_ratio")
    else:
        aligned["put_call_ratio"] = np.nan

    # 6. vix_pctl_1y (percentile of current VIX vs last 252d)
    if len(vix) >= 20:
        vix_aligned = _align_causal(vix, trading_dates, "vix")
        aligned["vix_pctl_1y"] = _expanding_percentile(vix_aligned, lookback=ZSCORE_LOOKBACK)
    else:
        aligned["vix_pctl_1y"] = np.nan

    # 7-8. Price structure variables
    if len(spy_close) >= 30:
        thermo = build_thermometer_frame(spy_close)
        # Align thermo vars (already daily, just reindex and shift for causality)
        aligned["phase_b_quiet"] = thermo["phase_b_quiet"].reindex(trading_dates).shift(1).ffill()
        aligned["retest_confirmed"] = thermo["retest_confirmed"].reindex(trading_dates).shift(1).ffill()
    else:
        aligned["phase_b_quiet"] = np.nan
        aligned["retest_confirmed"] = np.nan

    # 9. Current regime (for reference)
    aligned["regime"] = regime_series.reindex(trading_dates).ffill()

    # Return only the last row (as_of)
    result = aligned.iloc[-1].copy()
    result.name = as_of

    return result


def _expanding_zscore(series: pd.Series, lookback: int = 252) -> pd.Series:
    """Expanding z-score with minimum lookback window.

    For each point t, compute (x_t - mean_{t-lookback:t}) / std_{t-lookback:t}
    Using only data up to t (expanding window).
    """
    result = pd.Series(index=series.index, dtype=float)
    for i in range(len(series)):
        if i < lookback:
            result.iloc[i] = np.nan
        else:
            window = series.iloc[i-lookback:i+1]
            mean = window.mean()
            std = window.std(ddof=1)
            if std > 0:
                result.iloc[i] = (series.iloc[i] - mean) / std
            else:
                result.iloc[i] = np.nan
    return result


def _expanding_percentile(series: pd.Series, lookback: int = 252) -> pd.Series:
    """Expanding percentile rank (percentileofscore) with minimum lookback.

    For each point t, compute percentile of x_t within window t-lookback:t.
    """
    from scipy.stats import percentileofscore

    result = pd.Series(index=series.index, dtype=float)
    for i in range(len(series)):
        if i < lookback:
            result.iloc[i] = np.nan
        else:
            window = series.iloc[i-lookback:i+1].dropna()
            if len(window) > 10:
                result.iloc[i] = percentileofscore(window, series.iloc[i]) / 100.0
            else:
                result.iloc[i] = np.nan
    return result


# ============================================================================
# REGIME FINGERPRINT (TASK-008)
# ============================================================================

@dataclass
class RegimeFingerprint:
    """Statistics for a single regime."""
    regime: int
    regime_name: str
    n_obs: int
    variables: Dict[str, Dict[str, float]]  # var -> {median, iqr, pct_net_long}


def regime_fingerprint(
    zscores_df: pd.DataFrame,
    regime_series: pd.Series,
    regime: int,
    regime_name: str
) -> RegimeFingerprint:
    """Compute historical statistics for a specific regime.

    Args:
        zscores_df: DataFrame with z-score variables (index = dates)
        regime_series: Series with regime labels per date
        regime: Regime integer (0-3)
        regime_name: Semantic label (GOLDILOCKS, REFLATION, STAGFLATION, DEFLATION)

    Returns:
        RegimeFingerprint with median, IQR, % time net long per variable.
    """
    # Align dates
    common_dates = zscores_df.index.intersection(regime_series.index)
    if len(common_dates) == 0:
        return RegimeFingerprint(regime, regime_name, 0, {})

    z_aligned = zscores_df.loc[common_dates]
    reg_aligned = regime_series.loc[common_dates]

    # Filter to this regime
    mask = (reg_aligned == regime)
    if not mask.any():
        return RegimeFingerprint(regime, regime_name, 0, {})

    regime_data = z_aligned[mask]
    n_obs = len(regime_data)

    variables = {}
    for col in regime_data.columns:
        if col == "regime":
            continue
        vals = regime_data[col].dropna()
        if len(vals) > 0:
            median = float(vals.median())
            q75 = float(vals.quantile(0.75))
            q25 = float(vals.quantile(0.25))
            iqr = q75 - q25
            # % time net long: for z-scores, >0 = net long; for raw vars, >median
            if "z" in col.lower():
                pct_net_long = float((vals > 0).mean() * 100)
            else:
                pct_net_long = float((vals > median).mean() * 100)
            variables[col] = {
                "median": median,
                "iqr": iqr,
                "pct_net_long": pct_net_long,
            }

    return RegimeFingerprint(regime, regime_name, n_obs, variables)


def compute_all_fingerprints(
    zscores_df: pd.DataFrame,
    regime_series: pd.Series,
    labels: List[str] = ["GOLDILOCKS", "REFLATION", "STAGFLATION", "DEFLATION"]
) -> Dict[int, RegimeFingerprint]:
    """Compute fingerprints for all 4 regimes."""
    fingerprints = {}
    for i, label in enumerate(labels):
        fp = regime_fingerprint(zscores_df, regime_series, i, label)
        fingerprints[i] = fp
    return fingerprints


# ============================================================================
# IC GATE VALIDATION (Phase Gate 2)
# ============================================================================

def validate_ic_gate(
    zscores_df: pd.DataFrame,
    spy_returns: pd.Series,
    horizon: int = 21,
    min_ic: float = 0.02,
    max_pvalue: float = 0.0056  # Bonferroni: 0.05/9
) -> Dict[str, Dict[str, float]]:
    """Validate each variable against forward returns (IC Gate 2).

    Args:
        zscores_df: DataFrame with z-score variables (index = dates)
        spy_returns: Daily SPY returns (close-to-close)
        horizon: Forward return horizon in days
        min_ic: Minimum Spearman IC threshold
        max_pvalue: Maximum p-value (Bonferroni corrected)

    Returns:
        Dict with IC, p-value, and pass/fail for each variable.
    """
    # Compute forward returns
    fwd_ret = spy_returns.shift(-horizon).rolling(horizon).sum()  # approx 21d return

    results = {}
    zscore_vars = [c for c in zscores_df.columns if c != "regime"]

    for var in zscore_vars:
        # Align
        common = zscores_df[var].dropna().index.intersection(fwd_ret.dropna().index)
        if len(common) < 100:
            results[var] = {"ic": np.nan, "pvalue": np.nan, "pass": False, "n": len(common)}
            continue

        x = zscores_df.loc[common, var]
        y = fwd_ret.loc[common]

        # Spearman correlation
        ic, pval = spearmanr(x, y, nan_policy="omit")

        passed = (not np.isnan(ic)) and (abs(ic) > min_ic) and (pval < max_pvalue)

        results[var] = {
            "ic": float(ic) if not np.isnan(ic) else np.nan,
            "pvalue": float(pval) if not np.isnan(pval) else np.nan,
            "pass": bool(passed),
            "n": len(common),
        }

    return results


def build_zscores_panel(
    regime_series: pd.Series,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    freq: str = "D"
) -> pd.DataFrame:
    """Build full panel of z-scores for a date range (for IC gate validation).

    Walk-forward: for each date, compute_zscores with data up to that date.
    """
    date_range = pd.date_range(start=start_date, end=end_date, freq=freq)
    # Filter to dates present in regime_series
    valid_dates = [d for d in date_range if d in regime_series.index]

    rows = []
    for date in valid_dates:
        try:
            zs = compute_zscores(regime_series, date)
            rows.append(zs)
        except Exception as e:
            print(f"  Skipping {date}: {e}")
            continue

    if not rows:
        return pd.DataFrame()

    panel = pd.DataFrame(rows)
    panel.index = pd.DatetimeIndex([r.name for r in rows])
    return panel


if __name__ == "__main__":
    # Quick test
    print("Testing institutional_fingerprint...")

    # Test COT fetch
    print("\n1. Testing COT fetch (2019-2020)...")
    cot = fetch_cot_years([2019, 2020])
    print(f"   COT shape: {cot.shape}")
    print(f"   Columns: {list(cot.columns)}")
    print(cot.tail(3))

    # Test AAII fetch
    print("\n2. Testing AAII fetch...")
    aaii = fetch_aaii()
    print(f"   AAII shape: {aaii.shape}")
    print(aaii.tail(3))

    # Test FRED fetch
    print("\n3. Testing FRED fetch (WALCL)...")
    walcl = fetch_fred("WALCL")
    print(f"   WALCL shape: {walcl.shape}")
    print(walcl.tail(3))

    print("\n✅ All fetchers working!")
