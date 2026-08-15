"""Prueba integral del sistema Fortress Core con datos sintéticos."""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from app.core.indicators import calculate_all_indicators
from app.core.adaptive_risk import AdaptiveRiskManager
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.signal_engine import SignalEngine
from app.core.backtest_engine import BacktestEngine


def generate_synthetic_data(symbols, start="2015-01-01", end="2024-12-31", seed=42):
    """Genera datos OHLCV sintéticos para pruebas."""
    np.random.seed(seed)
    dates = pd.bdate_range(start=start, end=end)
    data = {}
    for i, symbol in enumerate(symbols):
        n = len(dates)
        drift = 0.0002 + i * 0.00001
        vol = 0.01 + i * 0.001
        returns = np.random.normal(drift, vol, n)
        close = 100 * np.exp(np.cumsum(returns))
        open_ = close * (1 + np.random.normal(0, 0.002, n))
        high = np.maximum(open_, close) * (1 + np.abs(np.random.normal(0, 0.003, n)))
        low = np.minimum(open_, close) * (1 - np.abs(np.random.normal(0, 0.003, n)))
        volume = np.random.uniform(1e6, 1e7, n)
        df = pd.DataFrame({
            "open": open_, "high": high, "low": low,
            "close": close, "volume": volume
        }, index=dates)
        data[symbol] = df
    return data


def test_indicators():
    """Test de indicadores técnicos."""
    df = generate_synthetic_data(["TEST"])["TEST"]
    result = calculate_all_indicators(df)
    assert "ema20" in result.columns
    assert "ema50" in result.columns
    assert "ema200" in result.columns
    assert "rsi14" in result.columns
    assert "macd" in result.columns
    assert "adx14" in result.columns
    assert "atr14" in result.columns
    assert "volume_ratio" in result.columns
    assert "momentum_12_1" in result.columns
    print("✅ Indicadores técnicos OK")


def test_risk_manager():
    """Test del gestor de riesgo adaptativo."""
    rm = AdaptiveRiskManager(initial_equity=25000)
    rm.update_regime(0)
    shares = rm.compute_position_size(25000, 100, 2.0)
    assert shares > 0
    assert shares <= 2500  # 10% max position

    rm.register_entry("AAPL", 100, shares)
    to_close = rm.check_all_stops(25000, {"AAPL": 80}, {"AAPL": 2.0}, datetime.now())
    assert len(to_close) > 0
    print("✅ Gestor de riesgo OK")


def test_regime_classifier():
    """Test del clasificador de régimen."""
    symbols = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "VIX"]
    data = generate_synthetic_data(symbols)
    classifier = GlobalRegimeClassifier()
    classifier.fit(data)
    result = classifier.predict_current_regime(data)
    assert "state" in result
    assert "state_name" in result
    assert "allocation" in result
    assert "confidence" in result
    print("✅ Clasificador de régimen OK")


def test_signal_engine():
    """Test del motor de señales."""
    data = generate_synthetic_data(["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "VIX"])
    classifier = GlobalRegimeClassifier()
    classifier.fit(data)
    engine = SignalEngine(classifier)

    stock_data = generate_synthetic_data(["AAPL"])["AAPL"]
    signal = engine.generate_signal(stock_data, "AAPL", 0)
    # Puede ser None si no cumple filtros, pero no debe fallar
    print("✅ Motor de señales OK")


def test_backtest():
    """Test del motor de backtesting."""
    tickers = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    market_tickers = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "VIX"]
    price_data = generate_synthetic_data(tickers)
    market_data = generate_synthetic_data(market_tickers)

    engine = BacktestEngine(initial_capital=25000)
    result = engine.run(
        price_data,
        market_data,
        datetime(2019, 1, 1),
        datetime(2024, 12, 31),
    )
    assert "equity_curve" in result
    assert "trades" in result
    assert "metrics" in result
    assert "monte_carlo" in result
    print("✅ Backtest OK")
    print(f"   Métricas: {result['metrics']}")


if __name__ == "__main__":
    print("=== PRUEBA INTEGRAL FORTRESS CORE ===\n")
    test_indicators()
    test_risk_manager()
    test_regime_classifier()
    test_signal_engine()
    test_backtest()
    print("\n✅✅✅ TODAS LAS PRUEBAS PASARON CORRECTAMENTE ✅✅✅")