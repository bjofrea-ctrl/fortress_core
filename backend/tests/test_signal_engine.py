import pandas as pd
import pytest

from app.core.indicators import calculate_all_indicators
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.signal_engine import SignalEngine
from app.core.probabilistic_engine import BayesianOnlineUpdater


@pytest.fixture
def engine():
    return SignalEngine(GlobalRegimeClassifier())


def _make_downtrend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Invierte el orden temporal de open/high/low/close (conserva el índice de
    fechas y el volumen) para convertir la tendencia alcista del fixture en
    una bajista real, preservando la volatilidad día a día — a diferencia de
    escalar por una constante, que no cambia la dirección de la tendencia.
    """
    reversed_df = df.copy()
    for col in ("open", "high", "low", "close"):
        reversed_df[col] = df[col].values[::-1]
    return reversed_df


# generate_signal() calcula los indicadores INTERNAMENTE y exige >=200 filas
# de OHLCV crudo de entrada (ver el guard `len(stock_data) < 200`) — no hay
# que pasarle el output de calculate_all_indicators(), que ya viene recortado
# por el warmup (~252 días para momentum_12_1/ema200).


def test_generate_signal_returns_none_for_short_history(engine, short_ohlcv_df):
    # Regresión del IndexError histórico (SESSION_LOG): antes de este guard,
    # un símbolo con <200 días de historial rompía todo el scan de universo.
    assert engine.generate_signal(short_ohlcv_df, "TEST", regime_state=0) is None


def test_generate_signal_returns_none_for_regime_3(engine, ohlcv_df):
    assert engine.generate_signal(ohlcv_df, "TEST", regime_state=3) is None


def test_generate_signal_returns_none_on_downtrend(engine, ohlcv_df):
    assert engine.generate_signal(_make_downtrend(ohlcv_df), "TEST", regime_state=0) is None


def test_generate_signal_returns_expected_shape_when_present(engine, ohlcv_df):
    # El fixture genérico pasa tendencia/RSI/ADX pero el volumen es ruido
    # puro y no siempre cumple volume_ratio >= 1.0 (flaky). Se fuerza un
    # volumen alto en los últimos días para garantizar que este test
    # realmente ejercite el camino positivo, no sólo el None.
    boosted = ohlcv_df.copy()
    boosted.loc[boosted.index[-5:], "volume"] = boosted["volume"].iloc[:-5].mean() * 3
    sig = engine.generate_signal(boosted, "TEST", regime_state=0)

    assert sig is not None, "el fixture debería calificar con el volumen forzado"
    assert sig["symbol"] == "TEST"
    assert sig["signal_type"] == "BUY"
    assert 0.0 <= sig["score"] <= 1.0
    assert sig["stop_loss"] < sig["entry_price"] < sig["take_profit"]
    assert sig["payoff_ratio"] > 0
    assert set(sig["factors"].keys()) == {"momentum", "rsi"}


def test_factor_weight_priors_sum_to_one(engine):
    for regime, weights in engine.factor_weights.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, f"régimen {regime} no suma 1"


def test_get_factor_weights_without_bayesian_updater_returns_priors(engine):
    weights = engine._get_factor_weights(0)
    assert weights == engine.factor_weights[0]


def test_get_factor_weights_with_updater_normalizes():
    updater = BayesianOnlineUpdater()
    se = SignalEngine(GlobalRegimeClassifier(), bayesian_updater=updater)
    # Sin evidencia todavía -> cae a los priors (mismo comportamiento que sin updater)
    weights = se._get_factor_weights(0)
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    # Con evidencia fuerte a favor de momentum, el peso de momentum debe subir
    for _ in range(20):
        updater.update("0_momentum", correct=True, base_weight=se.factor_weights[0]["momentum"])
        updater.update("0_rsi", correct=False, base_weight=se.factor_weights[0]["rsi"])
    weights_after = se._get_factor_weights(0)
    assert abs(sum(weights_after.values()) - 1.0) < 1e-9
    assert weights_after["momentum"] > weights_after["rsi"]


def test_rank_signals_sorts_descending(engine):
    signals = [{"score": 0.3}, {"score": 0.9}, {"score": 0.6}]
    ranked = engine.rank_signals(signals)
    assert [s["score"] for s in ranked] == [0.9, 0.6, 0.3]


def test_filter_by_regime_exposure_empty_when_already_at_max(engine):
    max_exposure = engine.regime_classifier.REGIME_ALLOCATION[0]["equity"]
    result = engine.filter_by_regime_exposure(
        signals=[{"symbol": "AAPL", "score": 0.9}],
        regime_state=0,
        current_exposure=max_exposure,
    )
    assert result == []


def test_compute_factor_frame_eligible_matches_generate_signal_rejection(engine, ohlcv_df):
    downtrend = _make_downtrend(ohlcv_df)

    frame = engine.compute_factor_frame(calculate_all_indicators(downtrend))
    last_eligible = bool(frame["eligible"].iloc[-1])
    sig = engine.generate_signal(downtrend, "TEST", regime_state=0)

    # Invariante real: si compute_factor_frame dice "no elegible", generate_signal
    # nunca puede devolver una señal para ese mismo día (el filtro duro es el mismo).
    if not last_eligible:
        assert sig is None
