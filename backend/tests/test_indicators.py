import numpy as np
import pandas as pd
from app.core.indicators import atr, calculate_all_indicators, ema, rsi

EXPECTED_COLUMNS = {
    "ema20", "ema50", "ema200", "rsi14", "macd", "macd_signal", "macd_hist",
    "adx14", "atr14", "volume_sma20", "volume_ratio", "momentum_12_1",
    "trend_bullish", "bb_upper", "bb_middle", "bb_lower", "stoch_k", "stoch_d",
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
