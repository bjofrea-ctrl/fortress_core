from typing import Tuple

import numpy as np
import pandas as pd

from app.core.predictive_indicators import compute_efficiency_ratio


def ema(prices: pd.Series, period: int) -> pd.Series:
    return prices.ewm(span=period, adjust=False).mean()


def sma(prices: pd.Series, period: int) -> pd.Series:
    return prices.rolling(window=period).mean()


def wma(prices: pd.Series, period: int) -> pd.Series:
    """Media móvil ponderada lineal (pesos 1..period, el más reciente pesa más)."""
    weights = np.arange(1, period + 1, dtype=float)
    return prices.rolling(window=period).apply(
        lambda x: float(np.dot(x, weights) / weights.sum()), raw=True
    )


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
                 volume: pd.Series, window: int = 20) -> pd.DataFrame:
    """Features derivados del CVD — acumulación rolling, pendiente y divergencia.

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
    """Exponente de Hurst por ventana — feature de régimen POR SÍMBOLO
    (T2.3, PLAN_INTEGRACION_INDICAGENT.md), complementaria al HMM macro
    (cross-asset), NO su reemplazo.

    Estimador de escalamiento de varianza sobre la TRAYECTORIA (cumsum de
    retornos log) de cada ventana: para un proceso fraccional
    Var(Z[t+τ] − Z[t]) ~ τ^(2H), por lo que la pendiente de log(std(Δτ Z))
    contra log(τ) es H. Random walk puro → H≈0.5; persistencia de tendencia
    (regímenes alcistas/bajistas o AR(1) con ρ>0) → H>0.5; reversión a la
    media → H<0.5. NO se quita la media/detrend dentro de la ventana: hacerlo
    convierte la trayectoria en puente browniano y sesga H hacia abajo en
    muestras finitas (medido: 0.39 vs 0.5 esperado para RW puro). Se hace
    sobre retornos (no sobre precios nivel) porque el nivel puro da H≈1.0
    por construcción.

    `min_periods=window//2`: 50 barras alcanzan para estimar y no quema 100
    filas extra de warmup. Ventanas con varianza degenerada (precio plano)
    devuelven NaN — el diagnóstico de IC decide cómo tratarlas. Costo
    O(n·max_lag) TOTAL (vectorizado con sliding_window_view), no por barra:
    seguro precomputar una vez por símbolo y también dentro del pipeline
    común (calculate_all_indicators).
    """
    def _hs(rets: np.ndarray) -> float:
        if len(rets) < max_lag + 2 or not np.isfinite(rets).all():
            return float("nan")
        z = np.cumsum(rets)  # trayectoria SIN detrend: el quita-media sesga
        lags = list(range(2, max_lag + 1))
        sigs = []
        for lag in lags:
            d = z[lag:] - z[:-lag]
            std_d = d.std(ddof=1)
            sigs.append(float(std_d) if std_d > 1e-12 else float("nan"))
        sigs = np.array(sigs)
        mask = np.isfinite(sigs) & (sigs > 0)
        if mask.sum() < max(3, len(lags) // 2):
            return float("nan")
        slope = np.polyfit(np.log(np.array(lags, dtype=float)[mask]),
                           np.log(sigs[mask]), 1)[0]
        return float(np.clip(slope, 0.0, 1.0))

    logret = np.log(close).diff().to_numpy()
    n = len(logret)
    out = np.full(n, np.nan)
    if n >= min_periods:
        # Vectorizado: en lugar de rolling().apply(_hs) por barra (loop Python
        # por ventana), se materializan todas las ventanas y se calcula el
        # estimador con operaciones numpy por bloque. Mismo algoritmo que _hs:
        # cumsum SIN detrend, std por lag con ddof=1, máscara de finitos,
        # polyfit de log(std) vs log(lag), clip [0,1]. Solo cambia el MECANISMO.
        from numpy.lib.stride_tricks import sliding_window_view

        # Ventanas completas (tamaño window) alineadas con el rolling() original:
        # out[t] = _hs(logret[t-window+1 : t+1]) para t >= window-1
        if n >= window:
            windows = sliding_window_view(logret, window)  # (n-window+1, window)
            z = np.cumsum(windows, axis=1)                 # trayectoria por ventana
            lags = np.arange(2, max_lag + 1, dtype=np.float64)
            # std por lag para TODAS las ventanas a la vez: (n-window+1, len(lags))
            sigs_all = np.empty((windows.shape[0], len(lags)))
            for j, lag in enumerate(lags):
                d = z[:, int(lag):] - z[:, :-int(lag)]
                sigs_all[:, j] = d.std(axis=1, ddof=1)
            valid = np.isfinite(sigs_all) & (sigs_all > 0)
            enough = valid.sum(axis=1) >= max(3, len(lags) // 2)
            log_lags = np.log(lags)
            for i in range(windows.shape[0]):
                if not enough[i]:
                    continue
                m = valid[i]
                slope = np.polyfit(log_lags[m], np.log(sigs_all[i, m]), 1)[0]
                out[window - 1 + i] = float(np.clip(slope, 0.0, 1.0))

        # Ventanas parciales (min_periods <= tamaño < window): replican el
        # comportamiento del rolling con min_periods para los primeros índices:
        # out[t] = _hs(logret[0 : t+1]) con longitud t+1 (>= min_periods).
        for t in range(min_periods - 1, min(window - 1, n)):
            out[t] = _hs(logret[: t + 1])

    return pd.Series(out, index=close.index)


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


def kama(prices: pd.Series, er_period: int = 10, fast: int = 2,
         slow: int = 30) -> pd.Series:
    """KAMA de Kaufman (Tarea M — PLAN_MEJORA_MATEMATICA §44): media móvil que
    ajusta su velocidad con el Efficiency Ratio (ER reusado de
    predictive_indicators.compute_efficiency_ratio — no reinventado, orden de la
    spec). ER→1 (movimiento direccional) acelera hacia fast_sc; ER→0 (choppy) se
    aplana hacia slow_sc.

    sc_t = (ER_t×(2/(fast+1) − 2/(slow+1)) + 2/(slow+1))²;
    recursión causal kama_t = kama_{t−1} + sc_t×(close_t − kama_{t−1}),
    sembrada en el primer close con ER válido. NaN antes del warmup y sobre
    series planas (volatility=0 → ER indefinido).
    """
    er = compute_efficiency_ratio(prices, er_period)
    fast_sc = 2.0 / (fast + 1.0)
    slow_sc = 2.0 / (slow + 1.0)
    sc = ((er * (fast_sc - slow_sc) + slow_sc) ** 2)
    vals = prices.values.astype(float)
    sc_vals = sc.values
    out = np.full(len(vals), np.nan)
    finite = np.flatnonzero(np.isfinite(sc_vals))
    if len(finite) == 0:
        return pd.Series(out, index=prices.index)
    start = int(finite[0])
    prev = vals[start]
    out[start] = prev
    for i in range(start + 1, len(vals)):
        prev += sc_vals[i] * (vals[i] - prev)
        out[i] = prev
    return pd.Series(out, index=prices.index)


def hma(prices: pd.Series, period: int = 16) -> pd.Series:
    """Hull Moving Average (Tarea M — PLAN_MEJORA_MATEMATICA §44), fórmula
    literal de Alan Hull (2005): WMA(2×WMA(n/2) − WMA(n), √n). Cancela parte
    del lag estructural de las medias móviles manteniendo el suavizado.
    NaN durante el warmup (~period + √period ruedas)."""
    half = wma(prices, max(1, period // 2))
    full = wma(prices, period)
    sqrt_p = max(1, int(round(float(np.sqrt(period)))))
    return wma(2.0 * half - full, sqrt_p)


def supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int = 10, multiplier: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """Supertrend (Tarea M — PLAN_MEJORA_MATEMATICA §44; Olivier Seban ~2009,
    sin origen académico — caveat registrado en PLAN_LARGO_PLAZO.md Tarea M).

    basic_ub/lb = hl2 ± multiplier×ATR(period); bandas finales con ratchet
    causal estándar (final_ub solo baja si basic_ub baja o close_{t−1} quedó
    por encima; simétrico para final_lb). Dirección binaria: flip a +1 cuando
    close cruza por encima de final_ub (venía bajista), a −1 cuando cruza por
    debajo de final_lb (venía alcista); sino arrastra el estado previo.
    Devuelve (linea, direccion): linea = banda final activa; direccion ∈
    {+1 alcista, −1 bajista}, NaN hasta el primer ATR válido.
    """
    atr_ = atr(high, low, close, period)
    hl2 = (high + low) / 2.0
    basic_ub = hl2 + multiplier * atr_
    basic_lb = hl2 - multiplier * atr_
    c = close.values.astype(float)
    bub = basic_ub.values.astype(float)
    blb = basic_lb.values.astype(float)
    n = len(c)
    line = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    finite = np.flatnonzero(np.isfinite(bub))
    if len(finite) == 0:
        return pd.Series(line, index=close.index), pd.Series(direction, index=close.index)
    start = int(finite[0])
    ub_prev, lb_prev = bub[start], blb[start]
    d_prev = 1.0 if c[start] > hl2.values[start] else -1.0
    line[start] = lb_prev if d_prev == 1.0 else ub_prev
    direction[start] = d_prev
    for i in range(start + 1, n):
        if bub[i] < ub_prev or c[i - 1] > ub_prev:
            ub = bub[i]
        else:
            ub = ub_prev
        if blb[i] > lb_prev or c[i - 1] < lb_prev:
            lb = blb[i]
        else:
            lb = lb_prev
        if d_prev == -1.0:
            d = 1.0 if c[i] > ub else -1.0
        else:
            d = -1.0 if c[i] < lb else 1.0
        line[i] = lb if d == 1.0 else ub
        direction[i] = d
        ub_prev, lb_prev, d_prev = ub, lb, d
    return (pd.Series(line, index=close.index),
            pd.Series(direction, index=close.index))


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
    # T2.3 (PLAN_INTEGRACION_INDICAGENT.md): features de régimen por símbolo.
    # Disponibles para diagnóstico de IC; NO wired a signal_engine sin medir.
    logret = np.log(df.close).diff()
    df["hurst_exponent"] = hurst_exponent(df.close, 100, 20)
    df["realized_vol_regime"] = realized_vol_regime(logret, 20, 100)
    # Tarea M (PLAN_MEJORA_MATEMATICA §44): familia de tendencia adaptativa.
    # Disponibles para diagnóstico de IC; NO wired a signal_engine sin trial.
    df["kama10"] = kama(df.close)
    df["hma16"] = hma(df.close)
    st_line, st_dir = supertrend(df.high, df.low, df.close)
    df["supertrend_line"] = st_line
    df["supertrend_side"] = st_dir
    df["kama_dist"] = (df.close - df["kama10"]) / df.close
    df["hma_dist"] = (df.close - df["hma16"]) / df.close
    return df.ffill().dropna()
