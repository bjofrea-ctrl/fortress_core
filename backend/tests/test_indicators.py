import numpy as np
import pandas as pd
from app.core.indicators import atr, calculate_all_indicators, ema, ofi_proxy, rsi

EXPECTED_COLUMNS = {
    "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist",
    "adx14", "atr14", "volume_sma20", "volume_ratio", "momentum_12_1",
    "trend_bullish", "bb_upper", "bb_middle", "bb_lower", "stoch_k", "stoch_d",
    # T1.1 (PLAN_INTEGRACION_INDICAGENT.md) — proxy OFI desde OHLCV puro
    "ofi_raw", "ofi_ewma_fast", "ofi_ewma_slow", "ofi_spike_z",
    "ofi_price_ret_z", "ofi_divergence",
}


def test_calculate_all_indicators_has_expected_columns(ohlcv_df):
    result = calculate_all_indicators(ohlcv_df)
    assert EXPECTED_COLUMNS.issubset(result.columns)


def test_calculate_all_indicators_drops_warmup_nans(ohlcv_df):
    result = calculate_all_indicators(ohlcv_df)
    assert not result.isna().any().any()
    assert len(result) > 0
    assert len(result) < len(ohlcv_df)  # el warmup de ema200/momentum_12_1 recorta filas


def test_calculate_all_indicators_short_data_returns_empty_not_crash(short_ohlcv_df):
    # Regresión: antes de un fix documentado en SESSION_LOG, dropna() podía
    # vaciar el DataFrame para símbolos con poco historial y signal_engine
    # tiraba IndexError al hacer .iloc[-1] sobre un DataFrame vacío.
    result = calculate_all_indicators(short_ohlcv_df)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


def test_rsi_bounded_between_0_and_100():
    prices = pd.Series(np.linspace(100, 150, 60) + np.sin(np.arange(60)))
    r = rsi(prices, 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_atr_is_non_negative(ohlcv_df):
    result = atr(ohlcv_df.high, ohlcv_df.low, ohlcv_df.close, 14).dropna()
    assert (result >= 0).all()


def test_ema_converges_to_constant_price():
    prices = pd.Series([50.0] * 60)
    result = ema(prices, 20)
    assert abs(result.iloc[-1] - 50.0) < 1e-6


def test_momentum_12_1_matches_manual_calc(ohlcv_df):
    result = calculate_all_indicators(ohlcv_df)
    raw = ohlcv_df["close"]
    for date in result.index[:5]:
        i = raw.index.get_loc(date)
        expected = (raw.iloc[i] / raw.iloc[i - 252] - 1) * 100
        assert abs(result.loc[date, "momentum_12_1"] - expected) < 1e-6


# ============================================================
# T1.1 — OFI proxy (PLAN_INTEGRACION_INDICAGENT.md)
# ============================================================

def test_ofi_proxy_matches_formula_manual():
    """Unitario de la fórmula: (close-low)/(high-low+eps) * volumen."""
    high = pd.Series([10.0, 20.0])
    low = pd.Series([5.0, 10.0])
    close = pd.Series([9.0, 12.0])
    volume = pd.Series([100.0, 200.0])
    result = ofi_proxy(high, low, close, volume)
    expected_0 = (9.0 - 5.0) / (10.0 - 5.0 + 1e-9) * 100.0  # ≈ 80
    expected_1 = (12.0 - 10.0) / (20.0 - 10.0 + 1e-9) * 200.0  # ≈ 40
    assert abs(result.iloc[0] - expected_0) < 1e-4
    assert abs(result.iloc[1] - expected_1) < 1e-4


def test_ofi_proxy_finite_on_zero_range_bars():
    """Barras sin rango (high == low == close, p.ej. días de límite) no
    producen NaN/Inf — el eps regulariza el denominador."""
    flat = pd.Series([42.0] * 5)
    result = ofi_proxy(flat, flat, flat, pd.Series([1_000.0] * 5))
    assert np.isfinite(result).all()

def test_ofi_proxy_positive_when_close_al_high_con_volumen_alto():
    """Criterio de aceptación 1: cierre pegado al high con volumen alto en
    varias barras consecutivas -> ofi_ewma_fast consistentemente positivo.
    (Test unitario via ofi_features: no depende del warmup de 252 días de
    calculate_all_indicators.)"""
    n = 80
    low = np.full(n, 100.0)
    high = np.full(n, 104.0)
    close = np.full(n, 103.8)  # pegado al high: (close-low)/(high-low) ≈ 0.95
    volume = np.full(n, 5_000_000.0)  # volumen alto
    feats = ofi_features(
        pd.Series(high), pd.Series(low), pd.Series(close), pd.Series(volume))
    # La serie cruda es un ratio [0,1] del rango × volumen -> siempre >= 0
    assert (feats["ofi_raw"] > 0).all()
    # El EWMA rápido converge a ~ (103.8-100)/4.0 * 5M ≈ 4.75M, claramente positivo
    tail = feats["ofi_ewma_fast"].iloc[-40:]
    assert (tail > 0).all()
    assert tail.mean() > 4_000_000
    # Y la divergencia es neutra-acá (precio plano -> price_z ≈ 0)
    assert abs(feats["ofi_price_ret_z"].iloc[-40:]).mean() < 0.5


def test_ofi_proxy_negative_pressure_when_close_al_low():
    """Simétrico: cierre pegado al low -> raw bajo (presión vendedora)."""
    n = 80
    close = np.full(n, 100.2)  # pegado al low de 100: ratio ≈ 0.05
    volume = np.full(n, 5_000_000.0)
    feats = ofi_features(
        pd.Series(np.full(n, 104.0)), pd.Series(np.full(n, 100.0)),
        pd.Series(close), pd.Series(volume))
    tail = feats["ofi_ewma_fast"].iloc[-40:]
    assert (tail > 0).all()  # el raw es >=0 por construcción
    # ...pero muy bajo: ≈ 0.05*5M=250k vs los 4.75M del caso bullish
    assert tail.mean() < 400_000


def test_ofi_divergence_directionality():
    """ofi_divergence positivo ↔ OFI más alcista que el precio ese día."""
    n = 260
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-02", periods=n)
    # Precio plano, OFI con spike fuerte (cierre al high, volumen 3x) al final
    base_close = np.full(n, 100.0) + rng.normal(0, 0.2, n)
    volume = np.full(n, 1_000_000.0)
    low = base_close - 1.0
    high = base_close + 1.0
    # últimas 15 barras: cierre pegado al high, volumen 3x
    base_close[-15:] = high[-15:] - 0.05
    volume[-15:] = 3_000_000.0
    df = pd.DataFrame({"open": base_close, "high": high, "low": low,
                       "close": base_close, "volume": volume}, index=dates)
    result = calculate_all_indicators(df)
    # Tras el régimen de presión compradora sin avance de precio, la divergencia
    # (OFI_z - price_z) debe ser positiva: OFI alcista sin confirmación de precio
    tail_div = result["ofi_divergence"].iloc[-5:]
    assert tail_div.mean() > 0


def test_ofi_no_breaks_warmup_with_short_panel(short_ohlcv_df):
    """Criterio 2: el z_window con min_periods=z_window//2 no exige 100 barras
    extra — paneles <252 filas siguen funcionando igual que antes de T1.1."""
    result = calculate_all_indicators(short_ohlcv_df)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0  # 50 filas = dropna por momentum_12_1, sin crash
