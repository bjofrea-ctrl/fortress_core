"""
Indicadores predictivos avanzados basados en investigación académica.
Implementa los 15 indicadores técnicos más fiables documentados en la literatura.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd


def compute_efficiency_ratio(close: pd.Series, period: int = 20) -> pd.Series:
    """
    Kaufman Efficiency Ratio (el del KAMA): |close_t - close_{t-period}| /
    sum(|close_i - close_{i-1}|) en la ventana.

    ER -> 1: movimiento lento, directo y sostenido (pasa desapercibido).
    ER -> 0: movimiento ruidoso de ida y vuelta (genera entusiasmo/miedo).

    Hipótesis V4 a validar: subidas lentas/eficientes predicen continuación;
    picos rápidos/ineficientes predicen reversión.
    """
    direction = close.diff(period).abs()
    volatility = close.diff().abs().rolling(window=period).sum()
    return (direction / volatility.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R: Sobrevendido < -80, sobrecompra > -20."""
    highest = df["high"].rolling(window=period).max()
    lowest = df["low"].rolling(window=period).min()
    return -100 * (highest - df["close"]) / (highest - lowest)


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Commodity Channel Index: > +100 sobrecompra, < -100 sobreventa."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad)


def parabolic_sar(df: pd.DataFrame, step: float = 0.02, max_step: float = 0.2) -> pd.Series:
    """Parabolic SAR: Trailing stop; puntos debajo del precio = alcista."""
    high, low = df["high"].values, df["low"].values
    close = df["close"].values
    n = len(df)
    sar = np.zeros(n)
    trend = np.zeros(n)  # 1 = uptrend, -1 = downtrend
    af = step

    if n < 2:
        return pd.Series(sar, index=df.index)

    # Initialize
    trend[0] = 1 if close[0] <= close[1] else -1
    if trend[0] == 1:
        sar[0] = low[0]
        ep = high[0]
    else:
        sar[0] = high[0]
        ep = low[0]

    for i in range(1, n):
        if trend[i-1] == 1:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = min(sar[i], low[i-1], low[i-2] if i >= 2 else low[i-1])
            if high[i] > ep:
                ep = high[i]
                af = min(af + step, max_step)
            if low[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep
                ep = low[i]
                af = step
            else:
                trend[i] = 1
        else:
            sar[i] = sar[i-1] + af * (ep - sar[i-1])
            sar[i] = max(sar[i], high[i-1], high[i-2] if i >= 2 else high[i-1])
            if low[i] < ep:
                ep = low[i]
                af = min(af + step, max_step)
            if high[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep
                ep = high[i]
                af = step
            else:
                trend[i] = -1

    return pd.Series(sar, index=df.index)


def donchian_channel(df: pd.DataFrame, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Donchian Channel: Upper (20d high), Lower (20d low), Mid."""
    upper = df["high"].rolling(window=period).max()
    lower = df["low"].rolling(window=period).min()
    mid = (upper + lower) / 2
    return upper, mid, lower


def money_flow_index(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index: Combina precio y volumen para medir presión de compra/venta."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]

    delta_tp = tp.diff()
    pos_mf = mf.where(delta_tp > 0, 0)
    neg_mf = mf.where(delta_tp < 0, 0)

    pos_sum = pos_mf.rolling(window=period).sum()
    neg_sum = neg_mf.rolling(window=period).sum()
    mfr = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + mfr))


def on_balance_volume(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume: Acumulación/distribución acumulada."""
    obv = np.zeros(len(df))
    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i-1]:
            obv[i] = obv[i-1] + df["volume"].iloc[i]
        elif df["close"].iloc[i] < df["close"].iloc[i-1]:
            obv[i] = obv[i-1] - df["volume"].iloc[i]
        else:
            obv[i] = obv[i-1]
    return pd.Series(obv, index=df.index)


def accumulation_distribution_line(df: pd.DataFrame) -> pd.Series:
    """A/D Line: Mide flujo de acumulación vs distribución."""
    hl = df["high"] - df["low"]
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl.replace(0, np.nan)
    ad = (clv * df["volume"]).cumsum()
    return ad.fillna(0)


def chaikin_money_flow(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """CMF: > 0.2 fuerte acumulación, < -0.2 fuerte distribución."""
    hl = df["high"] - df["low"]
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl.replace(0, np.nan)
    mfv = clv * df["volume"]
    return mfv.rolling(window=period).sum() / df["volume"].rolling(window=period).sum()


def force_index(df: pd.DataFrame, period: int = 13) -> pd.Series:
    """Force Index: (Close_i - Close_{i-1}) * Volume_i, suavizado con EMA."""
    fi = df["close"].diff() * df["volume"]
    return fi.ewm(span=period, adjust=False).mean()


def price_volume_trend(df: pd.DataFrame) -> pd.Series:
    """Price Volume Trend: (Close_i - Close_{i-1}) / Close_{i-1} * Volume_i acumulado."""
    pct = df["close"].pct_change()
    pvt = (pct * df["volume"]).cumsum()
    return pvt.fillna(0)


def volume_price_confirmation(df: pd.DataFrame, vol_period: int = 20) -> pd.Series:
    """Ratio de confirmación precio-volumen: > 1 alcista confirmada, < 1 distribución."""
    price_up = (df["close"].diff() > 0).astype(int)
    vol_ratio = df["volume"] / df["volume"].rolling(window=vol_period).mean()
    score = price_up * vol_ratio
    return score.rolling(window=5).mean()


def detect_volume_divergence(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """
    Detecta divergencias precio-volumen (señal de distribución institucional).
    Retorna: +1 si el precio sube con volumen decreciente (distribución),
    -1 si el precio baja con volumen creciente (capitulación).
    """
    price_change = df["close"].pct_change(lookback)
    vol_change = df["volume"].pct_change(lookback)

    divergence = pd.Series(0.0, index=df.index)
    divergence[(price_change > 0.05) & (vol_change < -0.1)] = 1.0  # Distribución
    divergence[(price_change < -0.05) & (vol_change > 0.1)] = -1.0  # Capitulación
    divergence[(price_change > 0.05) & (vol_change > 0.1)] = 0.5    # Tendencia confirmada
    return divergence


def smart_money_index_indicator(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """
    Proxi de Smart Money Index usando OHLC diario.
    Mide la posición del close vs open relativo al rango del día.
    Valores altos sugieren presión institucional al cierre (smart money).
    """
    smi = (df["close"] - df["open"]) / (df["high"] - df["low"]).replace(0, np.nan)
    return smi.rolling(window=lookback).mean().fillna(0)


def ichimoku_cloud(df: pd.DataFrame) -> pd.DataFrame:
    """Ichimoku Cloud: Tenkan, Kijun, Senkou A/B, Chikou."""
    tenkan = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
    kijun = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((df["high"].rolling(52).max() + df["low"].rolling(52).min()) / 2).shift(26)
    chikou = df["close"].shift(-26)

    result = pd.DataFrame({
        "ichimoku_tenkan": tenkan,
        "ichimoku_kijun": kijun,
        "ichimoku_senkou_a": senkou_a,
        "ichimoku_senkou_b": senkou_b,
        "ichimoku_chikou": chikou,
    })
    # Cloud es alcista si senkou_a > senkou_b y precio > nube
    result["ichimoku_cloud_bullish"] = (df["close"] > senkou_a) & (df["close"] > senkou_b) & (senkou_a > senkou_b)
    return result


def calculate_predictive_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula los 15 indicadores técnicos predictivos adicionales."""
    df = df.copy()

    # 1. Williams %R
    df["williams_r"] = williams_r(df)

    # 2. CCI
    df["cci"] = cci(df)

    # 3. Parabolic SAR
    df["parabolic_sar"] = parabolic_sar(df)
    df["sar_bullish"] = df["close"] > df["parabolic_sar"]

    # 4. Donchian Channel
    df["donchian_upper"], df["donchian_mid"], df["donchian_lower"] = donchian_channel(df)
    df["donchian_breakout_buy"] = df["close"] > df["donchian_upper"].shift(1)
    df["donchian_breakout_sell"] = df["close"] < df["donchian_lower"].shift(1)

    # 5. Money Flow Index
    df["mfi14"] = money_flow_index(df)

    # 6. On-Balance Volume
    df["obv"] = on_balance_volume(df)
    df["obv_sma20"] = df["obv"].rolling(20).mean()
    df["obv_trend_bullish"] = df["obv"] > df["obv_sma20"]

    # 7. Accumulation/Distribution Line
    df["ad_line"] = accumulation_distribution_line(df)
    df["ad_sma20"] = df["ad_line"].rolling(20).mean()
    df["ad_trend_bullish"] = df["ad_line"] > df["ad_sma20"]

    # 8. Chaikin Money Flow
    df["cmf20"] = chaikin_money_flow(df)

    # 9. Force Index
    df["force_index"] = force_index(df)
    df["force_index_ema"] = df["force_index"].ewm(span=13, adjust=False).mean()

    # 10. Price Volume Trend
    df["pvt"] = price_volume_trend(df)

    # 11. Volume-Price Confirmation
    df["vpc_score"] = volume_price_confirmation(df)

    # 12. Volume Divergence (detección de manipulación)
    df["volume_divergence"] = detect_volume_divergence(df)

    # 13. Smart Money Index proxy
    df["smi_proxy"] = smart_money_index_indicator(df)

    # 14. Ichimoku Cloud
    ichimoku = ichimoku_cloud(df)
    for col in ichimoku.columns:
        df[col] = ichimoku[col]

    # 15. RSI divergencia (detección de distribución)
    if "rsi14" in df.columns:
        rsi_20 = df["rsi14"].rolling(5).mean()
        close_20 = df["close"].rolling(5).mean()
        df["bearish_divergence"] = ((close_20 > close_20.shift(1)) & (rsi_20 < rsi_20.shift(1))).astype(int)
        df["bullish_divergence"] = ((close_20 < close_20.shift(1)) & (rsi_20 > rsi_20.shift(1))).astype(int)
    else:
        df["bearish_divergence"] = 0
        df["bullish_divergence"] = 0

    # 16. Kaufman Efficiency Ratio (V4: velocidad del movimiento)
    df["er10"] = compute_efficiency_ratio(df["close"], period=10)
    df["er20"] = compute_efficiency_ratio(df["close"], period=20)
    df["er60"] = compute_efficiency_ratio(df["close"], period=60)

    return df


# --- Análisis de correlaciones macro ---

MACRO_CORRELATIONS: Dict[str, Dict[str, float]] = {
    "DXY": {"gold": -0.35, "silver": -0.30, "sp500": -0.25, "bonds10y": 0.20, "oil": -0.30, "copper": -0.20},
    "gold": {"DXY": -0.35, "silver": 0.80, "sp500": 0.05, "bonds10y": -0.40, "oil": 0.20, "copper": 0.30},
    "silver": {"DXY": -0.30, "gold": 0.80, "sp500": 0.15, "bonds10y": -0.30, "oil": 0.30, "copper": 0.55},
    "sp500": {"DXY": -0.25, "gold": 0.05, "silver": 0.15, "bonds10y": -0.30, "oil": 0.10, "copper": 0.45},
    "bonds10y": {"DXY": 0.20, "gold": -0.40, "silver": -0.30, "sp500": -0.30, "oil": -0.25, "copper": -0.25},
    "oil": {"DXY": -0.30, "gold": 0.20, "silver": 0.30, "sp500": 0.10, "bonds10y": -0.25, "copper": 0.35},
    "copper": {"DXY": -0.20, "gold": 0.30, "silver": 0.55, "sp500": 0.45, "bonds10y": -0.25, "oil": 0.35},
}


def compute_gold_silver_ratio(gold: pd.Series, silver: pd.Series) -> pd.Series:
    """Gold/Silver ratio: > 80 miedo, < 65 optimismo en metales."""
    return gold / silver


def compute_correlation_strength(asset1: pd.Series, asset2: pd.Series, lookback: int = 60) -> float:
    """Calcula correlación móvil entre dos activos."""
    merged = pd.concat([asset1, asset2], axis=1).dropna().tail(lookback)
    if len(merged) < 30:
        return 0.0
    return float(merged.iloc[:, 0].corr(merged.iloc[:, 1]))
