import numpy as np
import pandas as pd
import pytest
from app.core.probabilistic_engine import CopulaRiskAnalyzer


@pytest.fixture
def analyzer():
    return CopulaRiskAnalyzer()


def _correlated_series(rho: float, n: int = 2000, seed: int = 0):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    y = rho * x + np.sqrt(max(1 - rho**2, 0)) * rng.normal(0, 1, n)
    return x, y


def test_fit_theta_scales_with_dependence_strength(analyzer):
    """
    Regresión: la MLE original (fit_clayton/fit_gumbel) tenía un error de
    signo y le faltaban términos en la log-verosimilitud — siempre convergía
    al límite del optimizador (theta≈0 / theta≈20) sin importar los datos.
    """
    strong_x, strong_y = _correlated_series(0.9)
    weak_x, weak_y = _correlated_series(0.2, seed=1)
    indep_x, indep_y = _correlated_series(0.0, seed=2)

    def thetas(x, y):
        u, v = analyzer._pseudo_observations(x), analyzer._pseudo_observations(y)
        return analyzer.fit_clayton(u, v), analyzer.fit_gumbel(u, v)

    strong_c, strong_g = thetas(strong_x, strong_y)
    weak_c, weak_g = thetas(weak_x, weak_y)
    indep_c, indep_g = thetas(indep_x, indep_y)

    assert strong_c > weak_c > indep_c
    assert strong_g > weak_g > indep_g
    assert indep_c == pytest.approx(0.0, abs=1e-3)
    assert indep_g == pytest.approx(1.0, abs=0.05)


def test_tail_dependence_increases_with_correlation(analyzer):
    strong_x, strong_y = _correlated_series(0.9)
    weak_x, weak_y = _correlated_series(0.2, seed=1)

    u1, v1 = analyzer._pseudo_observations(strong_x), analyzer._pseudo_observations(strong_y)
    u2, v2 = analyzer._pseudo_observations(weak_x), analyzer._pseudo_observations(weak_y)

    lambda_u_strong = analyzer.tail_dependence_gumbel(analyzer.fit_gumbel(u1, v1))
    lambda_u_weak = analyzer.tail_dependence_gumbel(analyzer.fit_gumbel(u2, v2))
    assert lambda_u_strong > lambda_u_weak


def test_analyze_macro_risks_does_not_crash_with_real_shaped_dataframes(analyzer):
    """
    Regresión: `macro_data.get(a) or macro_data.get(...)` rompía con
    ValueError ("truth value of a DataFrame is ambiguous") apenas
    macro_data.get(a) devolvía un DataFrame real de más de una fila.
    """
    dates = pd.bdate_range("2022-01-03", periods=400)
    rng = np.random.default_rng(3)
    macro_data = {
        "DXY": pd.DataFrame({"close": 100 + np.cumsum(rng.normal(0, 1, 400))}, index=dates),
        "gold": pd.DataFrame({"close": 1800 + np.cumsum(rng.normal(0, 5, 400))}, index=dates),
        "SPY": pd.DataFrame({"close": 400 + np.cumsum(rng.normal(0, 2, 400))}, index=dates),
    }
    results = analyzer.analyze_macro_risks(macro_data)
    assert "DXY_gold" in results
    assert "DXY_SPY" in results
    assert "error" not in results["DXY_gold"]
