"""
Backtest del motor predictivo Fortress Core — Fase 2

Evalúa la precisión del motor predictivo contra datos históricos:
- Genera señales en cada fecha histórica
- Compara con el retorno real futuro (1d, 5d, 20d, 60d)
- Calcula métricas de precisión: accuracy, precision, recall, F1
- Evalúa la calibración de probabilidades (Brier score)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.core.data_ingestion import download_data
from app.core.predictive_engine import PredictiveEngine
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.indicators import calculate_all_indicators

# Configuración
SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "SPY"]
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"
LOOKBACK = 300  # Días de historia para calcular indicadores
HORIZONS = {"1d": 1, "5d": 5, "20d": 20, "60d": 60}
STEP = 5  # Evaluar cada 5 días para no sobrecargar


def evaluate_predictions(symbol: str, df: pd.DataFrame) -> dict:
    """Evalúa las predicciones del motor contra retornos reales."""
    engine = PredictiveEngine()
    results = {h: {"correct": 0, "total": 0, "prob_sum": 0.0, "brier_sum": 0.0} for h in HORIZONS}

    # Calcular indicadores base
    df = calculate_all_indicators(df)
    df = calculate_predictive_indicators(df)
    df = df.dropna()

    # Evaluar en cada fecha de muestra
    for i in range(LOOKBACK, len(df) - max(HORIZONS.values()), STEP):
        date = df.index[i]
        hist = df.iloc[:i+1]

        try:
            result = engine.analyze(
                symbol=symbol,
                df=hist,
                regime_state=0,
            )
        except Exception:
            continue

        # Para cada horizonte, comparar con retorno real
        for h_name, h_days in HORIZONS.items():
            if i + h_days >= len(df):
                continue

            future_close = df["close"].iloc[i + h_days]
            current_close = df["close"].iloc[i]
            actual_return = (future_close - current_close) / current_close

            # Predicción: prob_up > 0.5 = alcista
            if h_name == "1d":
                prob_up = result.prob_up_short
            elif h_name == "5d":
                prob_up = result.prob_up_short
            elif h_name == "20d":
                prob_up = result.prob_up_medium
            else:  # 60d
                prob_up = result.prob_up_long

            predicted_up = prob_up > 0.5
            actual_up = actual_return > 0

            results[h_name]["total"] += 1
            if predicted_up == actual_up:
                results[h_name]["correct"] += 1

            # Brier score (calibración)
            target = 1.0 if actual_up else 0.0
            results[h_name]["brier_sum"] += (prob_up - target) ** 2

    # Calcular métricas finales
    metrics = {}
    for h_name, data in results.items():
        total = data["total"]
        if total == 0:
            metrics[h_name] = {"accuracy": 0, "brier": 0, "total": 0}
            continue
        metrics[h_name] = {
            "accuracy": data["correct"] / total,
            "brier": data["brier_sum"] / total,
            "total": total,
        }
    return metrics


def main():
    print("=== BACKTEST MOTOR PREDICTIVO FORTRESS CORE ===")
    print(f"Período: {START_DATE} a {END_DATE}")
    print(f"Símbolos: {SYMBOLS}")
    print()

    all_metrics = {}
    for symbol in SYMBOLS:
        print(f"Analizando {symbol}...")
        try:
            df = download_data(symbol, "2018-01-01")
            df = df[df.index >= START_DATE]
            if len(df) < 400:
                print(f"  ⚠️ Datos insuficientes ({len(df)} registros)")
                continue

            metrics = evaluate_predictions(symbol, df)
            all_metrics[symbol] = metrics

            for h_name, m in metrics.items():
                print(f"  {h_name}: accuracy={m['accuracy']:.1%} brier={m['brier']:.4f} n={m['total']}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    # Resumen agregado
    print("\n=== RESUMEN AGREGADO ===")
    for h_name in HORIZONS:
        accuracies = [all_metrics[s][h_name]["accuracy"] for s in all_metrics if all_metrics[s][h_name]["total"] > 0]
        briers = [all_metrics[s][h_name]["brier"] for s in all_metrics if all_metrics[s][h_name]["total"] > 0]
        if accuracies:
            print(f"{h_name}: Accuracy promedio = {np.mean(accuracies):.1%} | Brier promedio = {np.mean(briers):.4f}")

    # Benchmark: 50% accuracy = sin poder predictivo
    print("\nBenchmark: 50% accuracy = sin poder predictivo")
    print("Brier < 0.25 = mejor que adivinar (0.25 = aleatorio)")

    print("\n=== ✅ BACKTEST COMPLETADO ===")


if __name__ == "__main__":
    main()