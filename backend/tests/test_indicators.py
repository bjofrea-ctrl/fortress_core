import numpy as np
import pandas as pd
from app.core.indicators import (
    atr,
    calculate_all_indicators,
    cvd_features,
    cvd_proxy,
    ema,
    hurst_exponent,
    ofi_features,
    ofi_proxy,
    realized_vol_regime,
    rsi,
)

EXPECTED_COLUMNS = {
    "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist",
    "adx14", "atr14", "volume_sma20", "volume_ratio", "momentum_12_1",
    "trend_bullish", "bb_upper", "bb_middle", "bb_lower", "stoch_k", "stoch_d",
    # T1.1 (PLAN_INTEGRACION_INDICAGENT.md) — proxy OFI desde OHLCV puro
    "ofi_raw", "ofi_ewma_fast", "ofi_ewma_slow", "ofi_spike_z",
    "ofi_price_ret_z", "ofi_divergence",
    # T1.2 (PLAN_INTEGRACION_INDICAGENT.md) — proxy CVD desde OHLCV puro
    "cvd_bar_delta", "cvd_rolling", "cvd_slope_5bar", "cvd_divergence",
    # T2.3 (PLAN_INTEGRACION_INDICAGENT.md) — régimen por símbolo
    "hurst_exponent", "realized_vol_regime",
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


# ============================================================
# T1.2 — CVD proxy (PLAN_INTEGRACION_INDICAGENT.md)
# ============================================================

def test_cvd_proxy_matches_formula_manual():
    """Unitario de la fórmula: (2*close-high-low)/(high-low+eps) * volumen."""
    high = pd.Series([10.0, 20.0, 15.0])
    low = pd.Series([5.0, 10.0, 10.0])
    close = pd.Series([10.0, 15.0, 10.0])  # al high / al medio / al low
    volume = pd.Series([100.0, 200.0, 300.0])
    result = cvd_proxy(high, low, close, volume)
    # barra 0: cierre exactamente al high -> delta ≈ +100 (todo comprador)
    assert abs(result.iloc[0] - 100.0) < 1e-3
    # barra 1: cierre al medio -> delta ≈ 0
    assert abs(result.iloc[1]) < 1e-3
    # barra 2: cierre exactamente al low -> delta ≈ -300 (todo vendedor)
    assert abs(result.iloc[2] + 300.0) < 1e-3


def test_cvd_proxy_zero_on_flat_close_at_mid():
    """Cierre exactamente al medio del rango → delta cero aunque haya volumen."""
    high = pd.Series([110.0, 120.0])
    low = pd.Series([90.0, 100.0])
    close = pd.Series([100.0, 110.0])  # medio exacto
    volume = pd.Series([1_000_000.0, 2_000_000.0])
    result = cvd_proxy(high, low, close, volume)
    assert np.allclose(result.values, 0.0, atol=1e-3)


def test_cvd_rolling_matches_manual_window():
    """cvd_rolling(window) = suma de los últimos window deltas de barra."""
    n = 30
    rng = np.random.default_rng(3)
    high = pd.Series(100 + rng.uniform(1, 3, n))
    low = high - pd.Series(rng.uniform(2, 4, n))
    close = (high + low) / 2 + rng.uniform(-0.5, 0.5, n)
    volume = pd.Series(rng.uniform(1e5, 5e5, n))
    window = 7
    feats = cvd_features(high, low, close, volume, window=window)
    deltas = feats["cvd_bar_delta"]
    # Verifica la acumulacion rolling contra suma manual en un par de posiciones
    for i in (window, window + 5, n - 1):
        manual = deltas.iloc[i - window + 1:i + 1].sum()
        assert abs(feats["cvd_rolling"].iloc[i] - manual) < 1e-6


def test_cvd_divergence_direction():
    """cvd_divergence = sign(slope_5) - sign(price_change_5); flujo sin precio → 1."""
    n = 40
    high = pd.Series(np.full(n, 104.0))
    low = pd.Series(np.full(n, 100.0))
    # Cierre al high (flujo neto comprador fuerte y creciente) pero precio plano
    close = pd.Series(np.full(n, 103.9))
    volume = pd.Series(np.linspace(1e6, 5e6, n))  # volumen subiendo
    feats = cvd_features(high, low, close, volume, window=10)
    # precio no se mueve -> sign(close.diff(5))=0; flujo subiendo -> slope>0 -> +1
    tail = feats["cvd_divergence"].iloc[-5:]
    assert (tail == 1.0).all()


def test_calculate_all_indicators_includes_cvd_columns(ohlcv_df):
    """Las 4 columnas CVD aparecen en el pipeline completo."""
    result = calculate_all_indicators(ohlcv_df)
    for col in ("cvd_bar_delta", "cvd_rolling", "cvd_slope_5bar", "cvd_divergence"):
        assert col in result.columns


# ============================================================
# T2.3 — hurst_exponent + realized_vol_regime
# ============================================================

def test_hurst_exponent_random_walk_cerca_de_05():
    """Criterio de aceptación 1a: random walk puro → media de H razonablemente
    cerca de 0.5 (sesgo de muestra finito conocido, documentado en el docstring:
    ~0.41 con window=100, convergiendo a 0.5 con ventanas mayores — verificado
    empíricamente 2026-08-20: w=100→0.41, w=400→0.48, serie de 1999→0.49).
    No se exige |H−0.5|<ε exacto: se exige que NO colapse y que sea el punto
    medio de la escala, con σ acotada."""
    rng = np.random.default_rng(42)
    n = 800
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))))
    h = hurst_exponent(close, window=100, max_lag=20).dropna()
    assert len(h) > 600  # warmup acotado, masa disponible
    assert 0.30 <= h.mean() <= 0.60, f"H medio {h.mean():.3f} fuera del rango RW"
    assert h.std() < 0.15  # acotada, no bomba de varianza


def test_hurst_exponent_ar1_persistente_mayor_que_antipersistente():
    """Criterio de aceptación 1b: la DIFERENCIA entre procesos sí es robusta:
    AR(1) con ρ=0.7 (persistente) da H mayor que AR(1) con ρ=−0.5
    (anti-persistente). Verificado 2026-08-20: 0.66 vs 0.36."""
    rng = np.random.default_rng(7)
    n = 800
    r_pers, r_anti = np.zeros(n), np.zeros(n)
    for i in range(1, n):
        r_pers[i] = 0.7 * r_pers[i - 1] + rng.normal(0, 0.01)
        r_anti[i] = -0.5 * r_anti[i - 1] + rng.normal(0, 0.01)
    h_pers = hurst_exponent(pd.Series(100 * np.exp(np.cumsum(r_pers))), 100, 20).dropna()
    h_anti = hurst_exponent(pd.Series(100 * np.exp(np.cumsum(r_anti))), 100, 20).dropna()
    assert h_pers.mean() - h_anti.mean() > 0.2, (
        f"AR(0.7) H={h_pers.mean():.3f} no supera a AR(−0.5) H={h_anti.mean():.3f} "
        f"por el margen esperado ≥0.2")


def test_hurst_exponent_bounded_and_rolling_respects_index():
    rng = np.random.default_rng(1)
    n = 400
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))),
                      index=pd.bdate_range("2023-01-02", periods=n))
    h = hurst_exponent(close, window=50, max_lag=15)
    # bounded en [0,1] por construcción del clip + límite de pendiente
    assert h.dropna().between(0.0, 1.0).all()
    # warmup: con min_periods=window//2=25 y diff inicial, primeros valores NaN
    assert h.index.equals(close.index)
    assert len(h.dropna()) > 0


def test_realized_vol_regime_detecta_shock_de_volatilidad():
    """Cuando la vol reciente se multiplica, el ratio short/long sube sobre 1
    de forma estable; en calma tiende a ~1 (verificado empíricamente ~1.3 con
    ratio 3×)."""
    rng = np.random.default_rng(3)
    n = 300
    rets = pd.Series(np.concatenate([
        rng.normal(0, 0.005, n - 60),
        rng.normal(0, 0.025, 60),  # shock: vol 5× la de calma
    ]), index=pd.bdate_range("2023-01-02", periods=n))
    rv = realized_vol_regime(rets, 20, 100)
    assert rv.dropna().gt(1.2).iloc[-20:].all(), "el shock de vol debe elevar el ratio > 1.2"
    # post-shock parcial: el trailing largo va absorbiendo → ratio baja de a poco
    assert rv.iloc[-1] > rv.iloc[0]  # el régimen reciente es más volátil que el inicial


def test_calculate_all_indicators_includes_hurst_and_vol_regime(ohlcv_df):
    """Ambas columnas T2.3 aparecen en el pipeline completo."""
    result = calculate_all_indicators(ohlcv_df)
    for col in ("hurst_exponent", "realized_vol_regime"):
        assert col in result.columns
    # acotados a valores sensatos (hurst ∈ [0,1]; ratio > 0)
    assert result["hurst_exponent"].between(0.0, 1.0).all()
    assert (result["realized_vol_regime"] > 0).all()
