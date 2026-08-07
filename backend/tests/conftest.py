import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlcv_df():
    """OHLCV sintético con tendencia alcista suave, suficiente para el
    warmup de todos los indicadores (ema200/momentum_12_1 necesitan ~252d)."""
    n = 400
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2022-01-03", periods=n)
    drift = np.linspace(0, 40, n)
    noise = np.cumsum(rng.normal(0, 1, n))
    close = 100 + drift + noise
    close = np.maximum(close, 1.0)  # nunca precio negativo

    high = close + rng.uniform(0.1, 1.5, n)
    low = close - rng.uniform(0.1, 1.5, n)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.uniform(1_000_000, 5_000_000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def short_ohlcv_df(ohlcv_df):
    """Menos de 200 días — el caso que causaba el IndexError histórico."""
    return ohlcv_df.iloc[:50]
