from datetime import datetime
import json
import os
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

    mc = result["monte_carlo"]
    print("\n=== MONTE CARLO — bootstrap (resampling de trades) ===")
    for k, v in mc.get("bootstrap", {}).items():
        print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")
    print("\n=== MONTE CARLO — colas gruesas (t-Student + Cornish-Fisher VaR/ES) ===")
    for k, v in mc.get("fat_tail", {}).items():
        print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")

    print("\n=== CALIDAD DE SEÑAL (walk-forward IC) ===")
    sq = result.get("signal_quality", {})
    if "error" in sq:
        print(sq["error"])
    else:
        for k, v in sq.get("aggregate", {}).items():
            print(f"{k}: {v:.4f}" if isinstance(v, float) else f"{k}: {v}")

    # Save results to JSON for the frontend dashboard
    os.makedirs("data", exist_ok=True)

    # Convert dates to strings for JSON serialization
    for point in result.get("equity_curve", []):
        if hasattr(point["date"], "strftime"):
            point["date"] = point["date"].strftime("%Y-%m-%d")
    for trade in result.get("trades", []):
        if hasattr(trade["entry_date"], "strftime"):
            trade["entry_date"] = trade["entry_date"].strftime("%Y-%m-%d")
        if hasattr(trade["exit_date"], "strftime"):
            trade["exit_date"] = trade["exit_date"].strftime("%Y-%m-%d")

    with open("data/backtest_results.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n✅ Resultados guardados en data/backtest_results.json")
    print(f"   Dashboard disponible en http://localhost:3000")
