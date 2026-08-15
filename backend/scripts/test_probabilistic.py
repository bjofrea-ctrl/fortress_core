"""Prueba integral del motor probabilistico avanzado."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.probabilistic_engine import (
    BayesianOnlineUpdater,
    CopulaRiskAnalyzer,
    FatTailMonteCarlo,
    ProbabilityCalibrator,
    SignalQualityMetrics,
    WalkForwardValidator,
)


def test_calibrator():
    print("\n=== TEST 1: ProbabilityCalibrator ===")
    np.random.seed(42)
    n = 500
    true_probs = np.random.uniform(0.1, 0.9, n)
    scores = np.log(true_probs / (1 - true_probs)) + np.random.normal(0, 0.5, n)
    outcomes = (np.random.random(n) < true_probs).astype(float)
    cal = ProbabilityCalibrator(method="platt")
    cal.fit(scores, outcomes)
    probs = cal.predict(np.array([-2.0, 0.0, 2.0]))
    print(f"  A={cal.A:.4f}, B={cal.B:.4f}")
    print(f"  Probs: {[f'{p:.3f}' for p in probs]}")
    assert cal.is_fitted and all(0.05 <= p <= 0.95 for p in probs)
    print("  OK")


def test_signal_quality():
    print("\n=== TEST 2: SignalQualityMetrics ===")
    np.random.seed(42)
    n = 500
    # Generar retornos y una señal que predice el retorno FUTURO
    returns = np.random.normal(0.001, 0.02, n)
    # La señal de hoy predice el retorno de mañana
    signal = np.roll(returns, -1) * 0.5 + np.random.normal(0, 0.01, n)
    signal[-1] = 0  # Último valor no tiene futuro
    df = pd.DataFrame({"signal": signal, "close": (1 + returns).cumprod() * 100})
    m = SignalQualityMetrics.evaluate_signal(df, "signal", "close", horizon=1)
    print(f"  IC={m['ic']:.4f}, RankIC={m['rank_ic']:.4f}, ICIR={m['icir']:.4f}")
    assert abs(m["ic"]) > 0.1
    print("  OK")


def test_bayesian():
    print("\n=== TEST 3: BayesianOnlineUpdater ===")
    up = BayesianOnlineUpdater()
    for _ in range(20):
        up.update("momentum", True, 0.2)
    for _ in range(20):
        up.update("rsi", False, 0.15)
    wm, wr = up.get_weight("momentum"), up.get_weight("rsi")
    print(f"  momentum={wm:.4f}, rsi={wr:.4f}")
    assert wm > 0.2 and wr < 0.15
    print("  OK")


def test_monte_carlo():
    print("\n=== TEST 4: FatTailMonteCarlo ===")
    np.random.seed(42)
    returns = np.random.standard_t(df=3, size=500) * 0.02
    mc = FatTailMonteCarlo(n_sims=500, dof=5)
    m = mc.monte_carlo_metrics(returns)
    print(f"  Mean=${m['mean']:.0f}, P5=${m['p5']:.0f}, VaR={m['var_95']}%, ES={m['expected_shortfall_95']}%")
    assert m["var_95"] < 0 and m["expected_shortfall_95"] <= m["var_95"]
    print("  OK")


def test_copula():
    print("\n=== TEST 5: CopulaRiskAnalyzer ===")
    np.random.seed(42)
    n = 500
    z1 = np.random.normal(0, 1, n)
    z2 = np.random.normal(0, 1, n)
    mask = z1 < -1.5
    z2[mask] = z1[mask] * 0.8 + np.random.normal(0, 0.3, mask.sum())
    a = CopulaRiskAnalyzer()
    r = a.analyze_pair(z1, z2, "SPY", "VIX")
    print(f"  Pearson={r['pearson']:.4f}, Clayton={r['clayton_theta']:.4f}, TailL={r['tail_dependence_lower']:.4f}")
    assert "error" not in r
    print("  OK")


def test_walk_forward():
    print("\n=== TEST 6: WalkForwardValidator ===")
    np.random.seed(42)
    n = 1000
    returns = np.random.normal(0.001, 0.02, n)
    # Señal que predice retorno futuro a 5 días
    signal = np.roll(returns, -5) * 0.5 + np.random.normal(0, 0.01, n)
    signal[-5:] = 0
    df = pd.DataFrame({"signal": signal, "close": (1 + returns).cumprod() * 100})
    wf = WalkForwardValidator(train_window=252, test_window=63)
    r = wf.validate(df, "signal", horizon=5)
    print(f"  Windows={r['n_windows']}, MeanIC={r['mean_ic']:.4f}, ICIR={r['icir']:.4f}")
    assert "error" not in r
    print("  OK")


if __name__ == "__main__":
    print("=" * 60)
    print("FORTRESS CORE - TEST MOTOR PROBABILISTICO AVANZADO")
    print("=" * 60)
    test_calibrator()
    test_signal_quality()
    test_bayesian()
    test_monte_carlo()
    test_copula()
    test_walk_forward()
    print("\n" + "=" * 60)
    print("TODAS LAS PRUEBAS PROBABILISTICAS PASARON")
    print("=" * 60)
