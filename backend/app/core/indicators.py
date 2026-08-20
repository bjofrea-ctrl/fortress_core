from typing import Tuple

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
    return df.ffill().dropna()
