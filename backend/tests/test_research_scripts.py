"""Tests de las funciones puras de los scripts de investigación §11/§12:
panel, ridge purgado, PBO/CSCV y cointegración."""
import numpy as np
import pandas as pd
import pytest

from scripts.diagnose_pairs_cointegration import spread_stationary
from scripts.diagnose_ridge_combination import purged_folds
from scripts.pbo_cscv import sharpe


def test_purged_folds_exclude_overlap():
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    horizon = 20
    folds = list(purged_folds(dates.values, n_folds=5, horizon=horizon))

    assert len(folds) == 5
    for train_idx, test_idx in folds:
        assert len(np.intersect1d(train_idx, test_idx)) == 0
        test_dates = dates[test_idx]
        test_start, test_end = test_dates.min(), test_dates.max()
        # ninguna fila de train dentro de la zona de purga/embargo del test
        for i in train_idx:
            d = dates[i]
            assert not (test_start - pd.Timedelta(days=30) <= d <= test_end + pd.Timedelta(days=30)), \
                "fila de train solapa con test (purga/embargo no aplicada)"
    # las particiones cubren todo el rango
    all_idx = np.concatenate([t for _, t in folds])
    assert len(np.unique(all_idx)) == 200


def test_purged_folds_balanced_sizes():
    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    folds = list(purged_folds(dates.values, n_folds=5, horizon=20))
    sizes = [len(t) for _, t in folds]
    assert max(sizes) - min(sizes) <= 1, "folds desbalanceados"
    # tras la purga el train queda más chico que el total
    total = 500
    for tr, te in folds:
        assert len(tr) < total - len(te), "la purga no removió filas"


def test_sharpe_known_values():
    assert sharpe(np.array([1.0, 1.0])) == 0.0
    assert sharpe(np.array([])) == 0.0
    assert sharpe(np.array([1.0])) == 0.0  # n < 2 -> 0
    xs = np.array([1.0, -1.0, 1.0, -1.0])
    assert abs(sharpe(xs)) < 1e-12  # media 0
    xs2 = np.array([2.0, 2.0, 2.0, 2.0])
    assert sharpe(xs2) == 0.0  # desv 0 -> 0


def test_spread_stationary_detects_cointegrated():
    rng = np.random.default_rng(42)
    t = np.arange(300)
    common = np.cumsum(rng.normal(0, 1, 300))  # paseo aleatorio común
    x = np.exp(1.5 * common + rng.normal(0, 0.05, 300))
    y = np.exp(1.5 * common + rng.normal(0, 0.05, 300))
    assert spread_stationary(x, y, p=0.05), "dos series con tendencia común deben ser cointegradas"


def test_spread_stationary_rejects_independent():
    # adfuller tiene tasa de falsos positivos del 5% por diseño; con varias
    # semillas, la mayoría DEBE rechazar la cointegración espuria.
    n_rejected = 0
    n_trials = 5
    for seed in range(10, 10 + n_trials):
        rng = np.random.default_rng(seed)
        x = np.exp(np.cumsum(rng.normal(0, 1, 300)))
        y = np.exp(np.cumsum(rng.normal(0, 1, 300)))
        if not spread_stationary(x, y, p=0.05):
            n_rejected += 1
    assert n_rejected >= 4, f"solo {n_rejected}/{n_trials} rechazaron la cointegración espuria"


def test_correlation_flags():
    from scripts.diagnose_factor_correlation import FACTORS
    assert FACTORS == ["momentum_score", "rsi_score", "macro_composite", "sentiment_v1"]
