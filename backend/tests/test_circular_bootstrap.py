"""
T2.2 — PLAN_INTEGRACION_INDICAGENT.md (Fase 2): bootstrap de bloques
circulares para intervalos de confianza de métricas agregadas de backtest.

`circular_block_bootstrap_ci` da un CI no asintótico que preserva la
autocorrelación de la serie de retornos dentro de cada bloque. Estos tests
solo importan `probabilistic_engine` a propósito: `backtest_engine` importa
`indicators`, que otra sesión está editando en vivo (IndentationError no
commitado) y rompería la colección.

Criterios de aceptación del plan:
1. Serie IID conocida (normal) → el CI contiene el Sharpe verdadero ~95% de
   las veces en simulación repetida.
2. Serie con autocorrelación fuerte inyectada → el CI de bloques es más
   ancho que un CI asintótico ingenuo sobre la misma serie.
3. `-k bootstrap` en verde.
"""
import numpy as np
from app.core.probabilistic_engine import circular_block_bootstrap_ci
from scipy.stats import norm


def _sharpe_stat(r: np.ndarray) -> float:
    """Sharpe anualizado (misma definición que calculate_metrics, ddof=1)."""
    s = r.std(ddof=1)
    return float(r.mean() / s * np.sqrt(252)) if s > 0 else 0.0


def _naive_sharpe_ci(r: np.ndarray, alpha: float = 0.05):
    """CI asintótico IID (Lo 2002) sobre la MISMA serie, para comparar anchos."""
    sr_daily = r.mean() / r.std(ddof=1)
    se = np.sqrt((1 + 0.5 * sr_daily ** 2) / len(r)) * np.sqrt(252)
    z = norm.ppf(1 - alpha / 2)
    est = sr_daily * np.sqrt(252)
    return est - z * se, est + z * se


def test_ci_bootstrap_cubre_el_sharpe_verdadero_en_serie_iid():
    """Criterio 1: con datos IID conocidos, el CI bootstrap contiene el
    Sharpe de población ~95% de las veces en simulación repetida.

    Observado ~0.94 con esta configuración. El percentil-bootstrap del
    Sharpe es levemente anti-conservador (Lo 2002), por eso se exige >= 0.85
    (margen holgado sobre el 0.94 observado, pero aún detecta un CI roto que
    diera cobertura baja).
    """
    mu, sigma, n = 0.001, 0.01, 500
    true_sharpe = mu / sigma * np.sqrt(252)
    n_sims, n_bootstrap = 120, 500
    covered = 0
    for i in range(n_sims):
        returns = np.random.default_rng(i).normal(mu, sigma, n)
        lo, hi = circular_block_bootstrap_ci(
            returns, _sharpe_stat, block_size=20,
            n_bootstrap=n_bootstrap, seed=20000 + i,
        )
        covered += lo <= true_sharpe <= hi

    coverage = covered / n_sims
    assert coverage >= 0.85, f"coverage {coverage:.3f} < 0.85 (esperado ~0.95)"


def test_ci_bloques_mas_ancho_que_ci_asintotico_en_serie_autocorrelacionada():
    """Criterio 2: autocorrelación fuerte inyectada (AR(1) phi=0.6) → el CI
    de bloques circulares es MÁS ANCHO que el CI asintótico IID sobre la
    misma serie. Ese es el punto del método: cuantificar la incertidumbre
    real que el supuesto IID subestima.

    Determinista (seeds fijas): ratio de anchos observado ~2x.
    """
    phi, n = 0.6, 500
    rng = np.random.default_rng(7)
    eps = rng.normal(0, 0.01, n)
    returns = np.empty(n)
    returns[0] = eps[0]
    for t in range(1, n):
        returns[t] = phi * returns[t - 1] + eps[t]

    lo_naive, hi_naive = _naive_sharpe_ci(returns)
    lo, hi = circular_block_bootstrap_ci(returns, _sharpe_stat,
                                         block_size=20, n_bootstrap=1000, seed=42)

    width_block = hi - lo
    width_naive = hi_naive - lo_naive
    assert width_block > width_naive, (
        f"CI bootstrap ({width_block:.3f}) no más ancho que asintótico "
        f"({width_naive:.3f}) en serie autocorrelacionada"
    )
    assert width_block > 1.2 * width_naive, (
        "el ancho del CI de bloques debe ser claramente mayor (en este "
        f"setup determinista se observa ~2x, no {width_block / width_naive:.2f}x)"
    )


def test_ci_determinista_con_seed_y_tipos_de_retorno():
    """Criterio 3 (reproducibilidad): mismo seed → mismo CI exacto; sin
    seed → valores distintos; devuelve (lo, hi) flotantes con lo <= hi;
    serie vacía → (nan, nan) sin crash."""
    returns = np.random.default_rng(3).normal(0.001, 0.01, 300)

    lo1, hi1 = circular_block_bootstrap_ci(returns, _sharpe_stat, seed=123)
    lo2, hi2 = circular_block_bootstrap_ci(returns, _sharpe_stat, seed=123)
    lo3, hi3 = circular_block_bootstrap_ci(returns, _sharpe_stat, seed=124)
    lo_ns, hi_ns = circular_block_bootstrap_ci(returns, _sharpe_stat)

    assert (lo1, hi1) == (lo2, hi2), "mismo seed debe dar el mismo CI"
    assert (lo1, hi1) != (lo3, hi3), "seed distinta debe dar CI distinto"
    assert (lo1, hi1) != (lo_ns, hi_ns), "sin seed debe variar (no determinista)"
    assert isinstance(lo1, float) and isinstance(hi1, float)
    assert lo1 <= hi1

    lo_empty, hi_empty = circular_block_bootstrap_ci(np.array([]), _sharpe_stat)
    assert np.isnan(lo_empty) and np.isnan(hi_empty)
