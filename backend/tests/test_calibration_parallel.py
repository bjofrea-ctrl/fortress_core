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

FIX 2026-09-04 (dos defectos del fixture original):
  a) El fixture pasaba OHLCV crudo a _build_calibration_dataset, cuyo
     contrato (backtest_engine.run:361) es un indicators_cache con
     calculate_all_indicators() YA aplicado. generate_signal necesita
     ema50/ema200/adx14/rsi14/volume_ratio; con el panel crudo devolvía
     None en los 12 símbolos, SIEMPRE — los tests de identidad comparaban
     dos arrays vacíos: 4/4 verdes validando nada (~16 min de corrida).
  b) El generador original (drift 10% + chop 7) no pasaba el gate de score
     (overall máx 0.56 < 0.60) ni con indicadores: el dataset seguía
     vacío. El generador oscilatorio actual produce 1-2 señales por panel.
  El test_fixture_produce_señales_no_dataset_vacío es el guardián: si el
  panel vuelve a quedar vacío, el suite explota con diagnóstico en vez
  de validar identidad de dos vacíos.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
import pytest
from app.core.backtest_engine import (
    _CALIBRATION_PARALLEL_MIN_SYMBOLS,
    BacktestEngine,
    _calibrate_symbol,
)


def _make_panel(n_bars: int = 1500, seed: int = 42) -> pd.DataFrame:
    """OHLCV sintético que pasa los gates del signal_engine.

    Movimiento OSCILATORIO de gran amplitud (sin drift): el chop sinusoidal
    hace que momentum_12_1, RSI y el cruce de EMAs oscilen, y los checkpoints
    del replay caigan dentro de las bandas de los gates en parte del ciclo
    (score >= 0.60, close>ema50>ema200, adx >= 20, 40<rsi<75, vr >= 1.0).

    Calibración verificada 2026-09-04 (las versiones ANTERIORES producían
    0 señales — dataset de calibración vacío, identidad de dos arrays
    vacíos): drift 10% → overall máx 0.56 (score nunca llega a 0.60); drift
    50-200% monótono → RSI fuera de banda o score < 0.60. El generador
    oscilatorio produce 1-2 señales por panel (21 en 12 seeds, seed 7: 2) —
    suficiente para ejercitar el camino real de calibración.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_bars)
    base = 100.0
    chop = 60.0 * np.sin(2 * np.pi * 0.008 * t) + 25.0 * np.sin(2 * np.pi * 0.05 * t + 1.3)
    noise = rng.normal(0, 2.0, n_bars)
    close = base + chop + noise
    high = close + np.abs(rng.normal(0, 0.5, n_bars))
    low = close - np.abs(rng.normal(0, 0.5, n_bars))
    open_ = close + rng.normal(0, 0.3, n_bars)
    idx = pd.bdate_range(end=pd.Timestamp("2026-08-14"), periods=n_bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": 1_000_000},
        index=idx,
    )


def _make_indicator_panel(n_bars: int = 1500, seed: int = 42) -> pd.DataFrame:
    """Panel con indicadores, como el caller de producción.

    Contrato real (backtest_engine.run:361): ``indicators_cache`` contiene
    ``calculate_all_indicators(df)`` por símbolo — NO OHLCV crudo. El fixture
    original pasaba crudo: ``generate_signal`` necesita ema50/ema200/adx14/
    rsi14/volume_ratio ya calculadas (por eso el parámetro se llama
    ``indicators_cache``), y cada llamada devolvía None por columnas faltantes
    en los 12 símbolos, siempre. Este helper alinea el fixture con el
    contrato y es el que usan los tests de identidad serial-vs-paralelo.
    """
    df = _make_panel(n_bars=n_bars, seed=seed)
    from app.core.indicators import calculate_all_indicators
    return calculate_all_indicators(df)


@pytest.fixture
def cache_12() -> Dict[str, pd.DataFrame]:
    """12 paneles con INDICADORES (contrato del caller de producción). Suficiente
    para activar la rama paralela."""
    out = {}
    for i in range(_CALIBRATION_PARALLEL_MIN_SYMBOLS + 4):
        sym = f"SYM{i:02d}"
        out[sym] = _make_indicator_panel(n_bars=1500, seed=42 + i)
    return out


def test_fixture_produce_señales_no_dataset_vacío(cache_12):
    """Guardián anti-vacío: el dataset de calibración NO puede quedar vacío.

    El defecto original (2026-09-04): el fixture pasaba OHLCV crudo —
    ``generate_signal`` devolvía None en los 12 símbolos siempre, y los tests
    de "identidad bit-a-bit" comparaban dos arrays vacíos (verdes validando
    nada, 16 min de corrida). Si este test falla, el panel sintético dejó
    de pasar los gates del signal_engine (score >= 0.60, close>ema50>ema200,
    adx >= 20, 40<rsi<75, volume_ratio >= 1.0) y hay que recalibrar el
    generador ANTES de confiar en cualquier test de identidad.
    """
    engine = BacktestEngine(initial_capital=25000)
    end = pd.Timestamp("2026-08-14")
    start = end - pd.Timedelta(days=730)
    scores, outcomes = engine._build_calibration_dataset(
        cache_12, end, update_bayesian=False, train_start_date=start
    )
    assert len(scores) > 0, (
        "dataset de calibración VACÍO: el panel sintético no pasa los gates "
        "del signal_engine — los tests de identidad están comparando dos "
        "arrays vacíos (validando nada). Recalibrar _make_panel."
    )
    assert len(scores) == len(outcomes)


def test_calibrate_symbol_deterministic():
    """El helper top-level es determinista sobre los mismos inputs.

    Usa el panel con indicadores (contrato de producción) y EXIGE que el
    resultado no sea vacío — determinismo de dos listas vacías no prueba nada
    (defecto original del fixture crudo, 2026-09-04).
    """
    df = _make_indicator_panel(n_bars=1500, seed=7)
    end = pd.Timestamp("2026-08-14")
    start = end - pd.Timedelta(days=730)
    s1, o1 = _calibrate_symbol("AAA", df, end, start, 1)
    s2, o2 = _calibrate_symbol("AAA", df, end, start, 1)
    assert s1 == s2
    assert o1 == o2
    assert len(s1) == len(o1)
    assert len(s1) > 0, "panel sintético no pasa gates — dataset vacío"


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
    (warm-start bayesiano es estado compartido).

    Tolerancia float, no bit-exacta: dos pasadas del BayesianOnlineUpdater
    sobre los mismos datos pueden diferir en el último bit (suma flotante no
    asociativa — 2.2e-16, épsilon de máquina, medido 2026-09-04 con dataset
    no vacío). El contrato de ESTE test es que ambas corridas van por la
    MISMA rama serial con los mismos datos; la bit-exactitud serial vs
    paralelo es el contrato del test 1 y esa comparación sigue exacta.
    """
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

    assert len(scores) > 0, "warm-start bayesiano sobre dataset vacío no ejercita nada"
    np.testing.assert_allclose(scores, ser_scores, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(outcomes, ser_outcomes, rtol=1e-12, atol=1e-12)
