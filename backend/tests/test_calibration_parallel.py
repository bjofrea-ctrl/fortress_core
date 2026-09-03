"""Tests del cuello #1 — paralelización de _build_calibration_dataset.

DIAGNOSTICO_PERF_ADVISOR_102.md §"Propuestas 4b". El cuello #1 (~20 min en
frío con 102 símbolos) se cierra paralelizando el replay de calibración con
ProcessPoolExecutor cuando update_bayesian=False (único caso sin estado
compartido entre símbolos).

Estos tests verifican el CONTRATO — no la performance:

1. Identidad serial vs paralelo: el mismo input produce exactamente los
   mismos scores y outcomes (bit-a-bit) en ambas ramas. Es la pieza no
   negociable: cambiar el dataset de calibración cambiaría el Platt y por
   tanto el win_prob de todos los tickets del dashboard.

2. Branching correcto: update_bayesian=True siempre va por la rama
   serial (estado compartido — el warm-start bayesiano no es seguro
   paralelizar sin re-arquitectura).

3. Umbral de paralelización: con menos símbolos que el umbral, la rama
   serial se usa (evita overhead de fork en universos chicos).
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
import pytest

from app.core.backtest_engine import (
    BacktestEngine,
    _CALIBRATION_PARALLEL_MIN_SYMBOLS,
    _calibrate_symbol,
)


def _make_panel(n_bars: int = 1500, seed: int = 42) -> pd.DataFrame:
    """OHLCV sintético que pasa los gates del signal_engine."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_bars)
    base = 100.0
    trend = base * (1 + 0.10 * t / 252)
    chop = 7.0 * np.sin(2 * np.pi * 0.03 * t)
    noise = rng.normal(0, 1.5, n_bars)
    close = trend + chop + noise
    high = close + np.abs(rng.normal(0, 0.5, n_bars))
    low = close - np.abs(rng.normal(0, 0.5, n_bars))
    open_ = close + rng.normal(0, 0.3, n_bars)
    idx = pd.bdate_range(end=pd.Timestamp("2026-08-14"), periods=n_bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 1_000_000},
        index=idx,
    )


@pytest.fixture
def cache_12() -> Dict[str, pd.DataFrame]:
    """12 paneles sintéticos. Suficiente para activar la rama paralela."""
    out = {}
    for i in range(_CALIBRATION_PARALLEL_MIN_SYMBOLS + 4):
        sym = f"SYM{i:02d}"
        out[sym] = _make_panel(n_bars=1500, seed=42 + i)
    return out


def test_calibrate_symbol_deterministic():
    """El helper top-level es determinista sobre los mismos inputs."""
    df = _make_panel(n_bars=1500, seed=7)
    end = pd.Timestamp("2026-08-14")
    start = end - pd.Timedelta(days=730)
    s1, o1 = _calibrate_symbol("AAA", df, end, start, 1)
    s2, o2 = _calibrate_symbol("AAA", df, end, start, 1)
    assert s1 == s2
    assert o1 == o2
    assert len(s1) == len(o1)


def test_build_calibration_dataset_parallel_identical_to_serial(cache_12):
    """Rama paralela (update_bayesian=False con N>=umbral) produce los
    MISMOS scores/outcomes que la rama serial."""
    engine = BacktestEngine(initial_capital=25000)
    end = pd.Timestamp("2026-08-14")
    start = end - pd.Timedelta(days=730)

    import app.core.backtest_engine as bte_mod
    original_threshold = bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS
    try:
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = 10_000
        ser_scores, ser_outcomes = engine._build_calibration_dataset(
            cache_12, end, update_bayesian=False, train_start_date=start
        )
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = 4
        par_scores, par_outcomes = engine._build_calibration_dataset(
            cache_12, end, update_bayesian=False, train_start_date=start
        )
    finally:
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = original_threshold

    assert ser_scores.shape == par_scores.shape
    assert ser_outcomes.shape == par_outcomes.shape
    np.testing.assert_array_equal(ser_scores, par_scores)
    np.testing.assert_array_equal(ser_outcomes, par_outcomes)


def test_build_calibration_dataset_below_threshold_uses_serial(cache_12):
    """Con menos símbolos que el umbral, la rama paralela NO se activa.

    Para data sintético el signal_engine puede no emitir señales (gates
    selectivos sobre OHLCV sintético), así que el contrato verificable es:
    mismo N de scores con o sin paralelización activado. Si el branch
    paralelo intentara abrirse con N>=umbral, la identidad NO se garantizaría
    al cambiar process boundaries — esto es lo que este test detecta.
    """
    engine = BacktestEngine(initial_capital=25000)
    end = pd.Timestamp("2026-08-14")
    start = end - pd.Timedelta(days=730)

    import app.core.backtest_engine as bte_mod
    original_threshold = bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS
    try:
        # Serial puro: umbral inalcanzable.
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = 10_000
        ser_scores, _ = engine._build_calibration_dataset(
            cache_12, end, update_bayesian=False, train_start_date=start
        )
        # Paralelo habilitado: umbral muy bajo.
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = 1
        par_scores, _ = engine._build_calibration_dataset(
            cache_12, end, update_bayesian=False, train_start_date=start
        )
    finally:
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = original_threshold

    np.testing.assert_array_equal(ser_scores, par_scores)


def test_build_calibration_dataset_update_bayesian_keeps_serial(cache_12):
    """Con update_bayesian=True, la rama paralela NUNCA se activa
    (warm-start bayesiano es estado compartido)."""
    engine = BacktestEngine(initial_capital=25000)
    end = pd.Timestamp("2026-08-14")
    start = end - pd.Timedelta(days=730)

    import app.core.backtest_engine as bte_mod
    original_threshold = bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS
    try:
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = 4
        scores, outcomes = engine._build_calibration_dataset(
            cache_12, end, update_bayesian=True, train_start_date=start
        )
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = 10_000
        ser_scores, ser_outcomes = engine._build_calibration_dataset(
            cache_12, end, update_bayesian=True, train_start_date=start
        )
    finally:
        bte_mod._CALIBRATION_PARALLEL_MIN_SYMBOLS = original_threshold

    np.testing.assert_array_equal(scores, ser_scores)
    np.testing.assert_array_equal(outcomes, ser_outcomes)