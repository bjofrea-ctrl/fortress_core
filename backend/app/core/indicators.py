from typing import Tuple

import numpy as np
import pandas as pd


def ema(prices: pd.Series, period: int) -> pd.Series:
    return prices.ewm(span=period, adjust=False).mean()


def sma(prices: pd.Series, period: int) -> pd.Series:
    return prices.rolling(window=period).mean()


def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def macd(prices: pd.Series, fast=12, slow=26, signal=9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast, ema_slow = ema(prices, fast), ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1
    ).max(axis=1)
    return tr.rolling(window=period).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
    plus_dm = high.diff().clip(lower=0)
    minus_dm = -low.diff().clip(upper=0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1
    ).max(axis=1)
    atr_ = tr.rolling(window=period).mean()
    plus_di = 100 * plus_dm.rolling(window=period).mean() / atr_
    minus_di = 100 * minus_dm.rolling(window=period).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(window=period).mean()


def bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple:
    """Calcula las Bandas de Bollinger (superior, media, inferior)."""
    sma_vals = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma_vals + (std * std_dev)
    lower = sma_vals - (std * std_dev)
    return upper, sma_vals, lower


def ofi_proxy(high: pd.Series, low: pd.Series, close: pd.Series,
              volume: pd.Series) -> pd.Series:
    """Proxy de Order Flow Imbalance por barra, desde OHLCV puro (sin ticks).

    Adaptado de ``ofi.py`` de indicAgent (T1.1, PLAN_INTEGRACION_INDICAGENT.md):
    la posición del cierre dentro del rango intradía, ponderada por volumen.
    Cierre pegado al high con volumen alto → presión compradora; pegado al low
    → presión vendedora.
    """
    eps = 1e-9
    return (close - low) / (high - low + eps) * volume


def ofi_features(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
                 span_fast: int = 5, span_slow: int = 20,
                 z_window: int = 100) -> pd.DataFrame:
    """Features derivados del OFI — EWMA fast/slow, spike z-normalizado y
    divergencia OFI-vs-precio. Adaptado a barras DIARIAS vectorizadas (el original
    de indicAgent es incremental por (símbolo, timeframe) intradía; acá opera
    sobre el DataFrame completo de una vez, como el resto de indicators.py).

    Uso de min_periods = z_window // 2 en el z-score: 50 barras dan estimaciones
    más que suficientes de media/desvío para una normalización y evita quemar
    100 filas extra de warmup (el pipeline ya descarta 252 por momentum_12_1).

    Columnas devueltas (prefijo ``ofi_``)::

        ofi_raw          proxy crudo por barra (fracción [0,1] del rango × volumen)
        ofi_ewma_fast    EWMA span 5  — presión inmediata
        ofi_ewma_slow    EWMA span 20 — presión sostenida
        ofi_spike_z      z-score del proxy en ventana de 100 barras
        ofi_price_ret_z  z-score del cambio de precio en la misma ventana
        ofi_divergence   ofi_spike_z - ofi_price_ret_z (pos = OFI más alcista que el precio)
    """
    raw = ofi_proxy(high, low, close, volume)
    ofi_ewma_fast = raw.ewm(span=span_fast, adjust=False).mean()
    ofi_ewma_slow = raw.ewm(span=span_slow, adjust=False).mean()
    price_return = close.diff()
    min_p = z_window // 2
    ofi_spike_z = (raw - raw.rolling(z_window, min_periods=min_p).mean()) / (
        raw.rolling(z_window, min_periods=min_p).std() + 1e-9)
    price_return_z = (price_return - price_return.rolling(z_window, min_periods=min_p).mean()) / (
        price_return.rolling(z_window, min_periods=min_p).std() + 1e-9)
    return pd.DataFrame({
        "ofi_raw": raw,
        "ofi_ewma_fast": ofi_ewma_fast,
        "ofi_ewma_slow": ofi_ewma_slow,
        "ofi_spike_z": ofi_spike_z,
        "ofi_price_ret_z": price_return_z,
        "ofi_divergence": ofi_spike_z - price_return_z,
    })


def cvd_proxy(high: pd.Series, low: pd.Series, close: pd.Series,
              volume: pd.Series) -> pd.Series:
    """Proxy de delta de volumen por barra desde OHLCV puro (sin ticks).

    Adaptado de ``cvd.py`` de indicAgent (T1.2, PLAN_INTEGRACION_INDICAGENT.md):
    posición del cierre dentro del rango, centrada en cero y ponderada por
    volumen: cierre al high → todo el volumen se cuenta como comprador;
    cierre al low → todo como vendedor; cierre al medio → delta cero.
    """
    eps = 1e-9
    return (2 * close - high - low) / (high - low + eps) * volume


def cvd_features(high: pd.Series, low: pd.Series, close: pd.Series,
                 volume: pd.Series, window: int = 20) -> pd.DataFrame:    """Features derivados del CVD — acumulación rolling, pendiente y divergencia.

    DECISIÓN DE DISEÑO (documentada según exige T1.2): el original de indicAgent
    resetea el acumulador de CVD cada sesión intradía (09:30 ET). Fortress opera
    en barras DIARIAS — no hay "sesión" dentro de una barra, así que el reset por
    sesión NO aplica. Se eligió una ACUMULACIÓN ROLLING de ``window`` días
    (default 20 ~ 1 mes hábil, alineado a CALIBRATION_HORIZON_DAYS) en vez de un
    acumulador infinito: un acumulador sin límite acumula drift histórico sin
    relación con la presión reciente y no es comparable entre símbolos ni fechas.
    El valor de window es una decisión de diseño, NO medido — si el diagnóstico
    de IC pide otro window, se pre-registra y se vuelve a medir.

    Columnas devueltas::

        cvd_bar_delta   delta de la barra individual [-vol, +vol]
        cvd_rolling     suma de deltas de las últimas `window` barras
        cvd_slope_5bar  (cvd_rolling[t] - cvd_rolling[t-5]) / 5 — aceleración
        cvd_divergence  sign(cvd_slope_5bar) - sign(close.diff(5)): cúando el flujo
                        va en dirección distinta al precio (patrón de divergencia SMC)
    """
    bar_delta = cvd_proxy(high, low, close, volume)
    cvd_rolling = bar_delta.rolling(window).sum()
    cvd_slope_5bar = cvd_rolling.diff(5) / 5
    price_change_5 = close.diff(5)
    cvd_divergence = np.sign(cvd_slope_5bar) - np.sign(price_change_5)
    return pd.DataFrame({
        "cvd_bar_delta": bar_delta,
        "cvd_rolling": cvd_rolling,
        "cvd_slope_5bar": cvd_slope_5bar,
        "cvd_divergence": cvd_divergence,
    })


# ============================================================
# T2.3 — Features de régimen por símbolo (Hurst + vol de corto/largo plazo)
# ============================================================

def hurst_exponent(close: pd.Series, window: int = 100,
                   max_lag: int = 20, min_periods: int = 50) -> pd.Series:
    """Exponente de Hurst ajustado vía R/S. >0.5 = persistencia/tendencia,
    <0.5 = reversión a la media, ~0.5 = camino aleatorio. Se usa como feature
    de régimen POR SÍMBOLO que complementa al HMM macro — NO es su reemplazo.

    Rolling sobre la serie de retornos logarítmicos dentro de cada ventana
    (precios de nivel conducen a H≈1.0 por construcción; el log-return
    des-tendea y produce el H real). Estimador rescaled-range clásico:
    para cada lag tau en [2, max_lag), acumula la desviación promedio y el
    std por lag, log-log reg. Genera un valor por ventana (window='rolling',
    no expanding). Complejidad: O(window × max_lag) por barra → se precalcula
    UNA vez por símbolo por corrida (NO usar dentro del loop por fecha).

    Uso de min_periods=window//2: 50 barras dan estimaciones robustas y evita
    quemar 100 filas extra de warmup (el pipeline ya descarta 252 por
    momentum_12_1). Si la varianza estándar de la ventana es ~0 (precio plano)
    el resultado es NaN — luego fillna(0.5) para el CI diagnóstico.
    """
    def _hs(sig: np.ndarray) -> float:
        if len(sig) < max_lag * 2:
            return 0.5
        lags = list(range(2, max_lag + 1))
        tau_list = []
        for lag in lags:
            diffs = sig[lag:] - sig[:-lag]
            mean_diff = diffs.mean()
            demeaned = np.cumsum(diffs - mean_diff)
            R = demeaned.max() - demeaned.min()
            S = diffs.std(ddof=1)
            if S > 1e-12:
                tau_list.append(R / S)
            else:
                tau_list.append(np.nan)
        if sum(np.isfinite(tau_list)) < max_lag // 2:
            return 0.5
        log_lags = np.log(lags)
        log_tau = np.log(tau_list)
        mask = np.isfinite(log_tau) & np.isfinite(log_lags)
        if mask.sum() < 2:
            return 0.5
        # pendiente del log-log / 2 = H; clamp a [0,1]
        m = np.polyfit(log_lags[mask], log_tau[mask], 1)[0]
        return float(np.clip(0.5 * m, 0.0, 1.0))

    logret = np.log(close).diff()
    return logret.rolling(window, min_periods=min_periods).apply(_hs, raw=True)


def realized_vol_regime(returns: pd.Series, short_window: int = 20,
                        long_window: int = 100) -> pd.Series:
    """Proxy SIMPLE de régimen de volatilidad: ratio vol de corto plazo vs
    largo plazo. NO es un GARCH(1,1) real — ver la decisión explícita en
    PLAN_INTEGRACION_INDICAGENT.md T2.3: solo si el diagnóstico de IC muestra
    poder predictivo del proxy se evalúa migrar a un GARCH completo
    (dependencia nueva `arch`), no antes. Uso diagnóstico, NO es gate ni señal.

    Ratio > 1: volatilidad subiendo (short > long); < 1: bajando.
    Ventanas rolling, resultados en escala [0, ∞). Si long_window es ~0 o
    indeterminado devuelve NaN.
    """
    short_vol = returns.rolling(short_window).std()
    long_vol = returns.rolling(long_window).std()
    return short_vol / (long_vol + 1e-12)


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema20"] = ema(df.close, 20)
    df["ema50"] = ema(df.close, 50)
    df["ema200"] = ema(df.close, 200)
    df["rsi14"] = rsi(df.close, 14)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(df.close)
    df["adx14"] = adx(df.high, df.low, df.close, 14)
    df["atr14"] = atr(df.high, df.low, df.close, 14)
    df["volume_sma20"] = sma(df.volume, 20)
    df["volume_ratio"] = df.volume / df.volume_sma20
    df["momentum_12_1"] = df.close.pct_change(252) * 100
    df["trend_bullish"] = (df.close > df.ema50) & (df.ema50 > df.ema200)
    # Bollinger Bands
    df["bb_upper"], df["bb_middle"], df["bb_lower"] = bollinger_bands(df.close, 20, 2.0)
    # Stochastic Oscillator
    low_14 = df.low.rolling(window=14).min()
    high_14 = df.high.rolling(window=14).max()
    df["stoch_k"] = 100 * (df.close - low_14) / (high_14 - low_14)
    df["stoch_d"] = df["stoch_k"].rolling(window=3).mean()
    # OFI proxy (T1.1 — PLAN_INTEGRACION_INDICAGENT.md): disponible para
    # diagnóstico de IC; NO está wired a signal_engine hasta que se mida.
    for col, series in ofi_features(df.high, df.low, df.close, df.volume).items():
        df[col] = series
    # CVD proxy (T1.2 — PLAN_INTEGRACION_INDICAGENT.md): misma condición.
    for col, series in cvd_features(df.high, df.low, df.close, df.volume).items():
        df[col] = series
    return df.ffill().dropna()
