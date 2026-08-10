"""Tests de la capa de régimen de sentimiento V1 (AAII bull-bear).

PLAN_SENTIMIENTO.md §7: peso dominante 0.50 pre-registrado. Estos tests
congelan el comportamiento del blend, el cuestionamiento H6 en euforia y
las reglas V4 de velocidad, para que una futura re-validación (que cambie
el peso) rompa los tests en lugar de pasar silenciosa.
"""
import numpy as np
import pandas as pd
import pytest

from app.core.predictive_engine import PredictiveEngine
from app.core.triad_agents import ContrarianAgent, TriadConsensus
from app.core.sentiment_regime import (
    SENTIMENT_REGIME_DOMINANCE,
    SENTIMENT_PANIC_SPREAD,
    SENTIMENT_EUPHORIA_SPREAD,
)


@pytest.fixture
def engine(monkeypatch):
    eng = PredictiveEngine()

    # La tríada llama a NIM (HTTP) — neutralizarla para aislar el blend V1
    def _fake_evaluate(*args, **kwargs):
        return TriadConsensus()  # consensus_score=0 -> no altera el composite

    monkeypatch.setattr(eng.triad_evaluator, "evaluate", _fake_evaluate)
    return eng


def _analyze(engine, ohlcv_df, **sentiment_kwargs):
    """Corre analyze() con datos de sentimiento opcionales."""
    return engine.analyze(
        "TEST", ohlcv_df, regime_state=0,
        sentiment_data=sentiment_kwargs or None,
    )


def test_blend_dominance_is_preregistered_050():
    """El peso 0.50 es la pre-registración §7 — cambiarlo debe revisarse."""
    assert SENTIMENT_REGIME_DOMINANCE == 0.50


def test_without_sentiment_data_is_backward_compatible(engine, ohlcv_df):
    """Sin datos de sentimiento (None o {}) el resultado es el baseline."""
    base = _analyze(engine, ohlcv_df)
    empty = _analyze(engine, ohlcv_df, aaii_bullbear_spread=None)
    assert empty.composite_score == pytest.approx(base.composite_score)
    assert empty.decision == base.decision


def test_neutral_sentiment_dilutes_composite(engine, ohlcv_df):
    """Spread 0 -> señal V1 neutra: el blend 50/50 amortigua la convicción
    base a la mitad (diseño fiel al bloque H7: 0.5*G1 + 0.5*0)."""
    base = _analyze(engine, ohlcv_df)
    neutral = _analyze(engine, ohlcv_df, aaii_bullbear_spread=0.0)
    assert neutral.composite_score == pytest.approx(0.5 * base.composite_score, abs=1e-6)


def test_panic_sentiment_tilts_bullish(engine, ohlcv_df):
    """Pesimismo extremo (spread muy negativo) desplaza el compuesto alcista."""
    base = _analyze(engine, ohlcv_df)
    panic = _analyze(engine, ohlcv_df, aaii_bullbear_spread=SENTIMENT_PANIC_SPREAD - 15.0)
    # s_v1 ~ +0.86 (satura en +1 solo fuera del bound), blend 0.5 + V4 +0.10
    assert panic.composite_score > base.composite_score + 0.25


def test_euphoria_sentiment_tilts_bearish(engine, ohlcv_df):
    """Euforia (spread muy positivo) desplaza el compuesto bajista."""
    base = _analyze(engine, ohlcv_df)
    euphoria = _analyze(engine, ohlcv_df, aaii_bullbear_spread=SENTIMENT_EUPHORIA_SPREAD + 15.0)
    assert euphoria.composite_score < base.composite_score - 0.4


def test_extreme_euphoria_questions_reversion(engine, ohlcv_df):
    """H6: euforia extrema agrega la señal de cuestionamiento al reporte."""
    result = _analyze(engine, ohlcv_df, aaii_bullbear_spread=SENTIMENT_EUPHORIA_SPREAD + 15.0)
    names = [s.name for s in result.signals]
    assert "Cuestionamiento euforia (H6)" in names
    assert "Sentiment Regime V1 (AAII)" in names


def test_signal_value_is_inverted_spread(engine, ohlcv_df):
    """La señal V1 es -normalize(spread): pesimismo -> +1 (alcista)."""
    from app.core.predictive_engine import AAII_SPREAD_BOUND  # noqa: F401

    result = _analyze(engine, ohlcv_df, aaii_bullbear_spread=0.0)
    v1 = [s for s in result.signals if s.name == "Sentiment Regime V1 (AAII)"]
    assert v1 and v1[0].signal == pytest.approx(0.0)

    result = _analyze(engine, ohlcv_df, aaii_bullbear_spread=-AAII_SPREAD_BOUND)
    v1 = [s for s in result.signals if s.name == "Sentiment Regime V1 (AAII)"]
    assert v1 and v1[0].signal == pytest.approx(1.0)


@pytest.fixture
def contrarian():
    return ContrarianAgent()


def _contrarian_score(contrarian, df, sentiment=None):
    return contrarian.evaluate(df, sentiment_data=sentiment).score


def test_contrarian_without_sentiment_backward_compatible(contrarian, ohlcv_df):
    assert _contrarian_score(contrarian, ohlcv_df) == _contrarian_score(contrarian, ohlcv_df, {})


def test_contrarian_panic_is_bullish(contrarian, ohlcv_df):
    assert _contrarian_score(contrarian, ohlcv_df,
                             {"aaii_bullbear_spread": SENTIMENT_PANIC_SPREAD - 10.0}) > 0.2


def test_contrarian_euphoria_is_bearish(contrarian, ohlcv_df):
    assert _contrarian_score(contrarian, ohlcv_df,
                             {"aaii_bullbear_spread": SENTIMENT_EUPHORIA_SPREAD + 10.0}) < -0.2
