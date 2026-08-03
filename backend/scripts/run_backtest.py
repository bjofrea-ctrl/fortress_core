from datetime import datetime
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe

if __name__ == "__main__":
    tickers = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    market_tickers = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]

    print("Descargando datos...")
    # Download market_data first (wider date range) so cache covers full range
    market_data = load_universe(market_tickers, "2015-01-01", "2024-12-31")
    price_data = load_universe(tickers, "2019-01-01", "2024-12-31")

    print("Ejecutando backtest...")
    engine = BacktestEngine(initial_capital=25000)
    result = engine.run(
        price_data,
        market_data,
        datetime(2019, 1, 1),
        datetime(2024, 12, 31),
    )

    print("\n=== MÉTRICAS ===")
    for k, v in result["metrics"].items():
        print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")

    print("\n=== MONTE CARLO ===")
    for k, v in result["monte_carlo"].items():
        print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")