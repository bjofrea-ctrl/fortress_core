import numpy as np
import pandas as pd
import pytest
from app.core.indicators import calculate_all_indicators
from app.core.probabilistic_engine import BayesianOnlineUpdater
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.signal_engine import SignalEngine


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


# --- T1.4: stop/target estructural + puerta RR (PLAN_INTEGRACION_INDICAGENT.md) ---

def _boosted_ohlcv(ohlcv_df) -> pd.DataFrame:
    """Fixture que SIEMPRE califica: volumen 3x en los últimos días."""
    boosted = ohlcv_df.copy()
    boosted.loc[boosted.index[-5:], "volume"] = boosted["volume"].iloc[:-5].mean() * 3
    return boosted


def test_generate_signal_none_structure_identico_al_baseline(engine, ohlcv_df):
    """Criterio 1 del ticket: con market_structure=None el comportamiento es
    IDÉNTICO al pre-T1.4 (stop = entry−2·ATR, target = entry+4·ATR, RR 2.0
    exacto: la puerta MIN_RR=1.5 es transparente sobre el fallback)."""
    sig = engine.generate_signal(_boosted_ohlcv(ohlcv_df), "TEST", regime_state=0)
    assert sig is not None, "el fixture con volumen forzado debe calificar"
    from app.core.indicators import calculate_all_indicators
    ind = calculate_all_indicators(_boosted_ohlcv(ohlcv_df))
    atr_v = ind.iloc[-1].atr14
    entry = ind.iloc[-1].close
    assert abs(sig["stop_loss"] - (entry - 2.0 * atr_v)) < 1e-9
    assert abs(sig["take_profit"] - (entry + 4.0 * atr_v)) < 1e-9
    assert abs(sig["payoff_ratio"] - 2.0) < 1e-9
    assert sig["structural_resolution"] is False


def test_resolve_stop_uses_order_block_under_entry(engine, ohlcv_df):
    """Criterio 2 del ticket: OB alcista no mitigado debajo del entry → el
    stop cae a ob_bottom − 0.20·ATR en vez del fallback."""
    from app.core.signal_engine import _resolve_stop
    entry, atr_v = 100.0, 2.0
    ms = {"order_block": {"ob_type": 1, "ob_mitigated": False,
                          "ob_top": 97.0, "ob_bottom": 96.0}}
    assert abs(_resolve_stop(entry, atr_v, ms) - (96.0 - 0.20 * 2.0)) < 1e-9
    # OB mitigado → cae al siguiente match (swing low si existe, sino fallback)
    ms_mit = {"order_block": {"ob_type": 1, "ob_mitigated": True,
                              "ob_top": 97.0, "ob_bottom": 96.0}}
    assert abs(_resolve_stop(entry, atr_v, ms_mit) - (entry - 2.0 * atr_v)) < 1e-9
    # OB por encima del entry no aplica para un BUY
    ms_above = {"order_block": {"ob_type": 1, "ob_mitigated": False,
                                "ob_top": 103.0, "ob_bottom": 102.0}}
    assert abs(_resolve_stop(entry, atr_v, ms_above) - (entry - 2.0 * atr_v)) < 1e-9
    # sweep presente califica entre OB y swing low
    ms_sweep = {"liquidity_sweep": {"sweep_detected": True, "sweep_type": 1,
                                    "sweep_level": 94.0}}
    assert abs(_resolve_stop(entry, atr_v, ms_sweep) - (94.0 - 0.30 * 2.0)) < 1e-9
    # nearest_swing_low califica antes del fallback
    ms_sw = {"nearest_swing_low": 92.0}
    assert abs(_resolve_stop(entry, atr_v, ms_sw) - (92.0 - 0.25 * 2.0)) < 1e-9


def test_rr_gate_rejected_when_target_too_close(engine, ohlcv_df):
    """Criterio 3 del ticket: target estructural más cercano deja RR < MIN_RR
    → generate_signal devuelve None (no "recorta" la señal)."""
    from app.core.indicators import calculate_all_indicators
    boosted = _boosted_ohlcv(ohlcv_df)
    ind = calculate_all_indicators(boosted)
    entry, atr_v = ind.iloc[-1].close, ind.iloc[-1].atr14
    # Resistencia a entry + 1·ATR → RR = 1/2 = 0.5 < 1.5 → rechazada
    ms_bad_rr = {"nearest_resistance": entry + 1.0 * atr_v}
    # control: sin estructura la misma señal SÍ existe
    assert engine.generate_signal(boosted, "TEST", regime_state=0) is not None
    assert engine.generate_signal(boosted, "TEST", regime_state=0,
                                  market_structure=ms_bad_rr) is None


def test_rr_gate_accepts_with_structural_target_far_enough(engine, ohlcv_df):
    """Con target estructural lejano (RR ≥ MIN_RR) la señal se genera y
    reporta la resolución estructural con payoff consistente."""
    from app.core.indicators import calculate_all_indicators
    boosted = _boosted_ohlcv(ohlcv_df)
    ind = calculate_all_indicators(boosted)
    entry, atr_v = ind.iloc[-1].close, ind.iloc[-1].atr14
    ms_ok = {"nearest_resistance": entry + 6.0 * atr_v}
    sig = engine.generate_signal(boosted, "TEST", regime_state=0,
                                 market_structure=ms_ok)
    assert sig is not None
    assert sig["structural_resolution"] is True
    assert abs(sig["take_profit"] - (entry + 6.0 * atr_v)) < 1e-9
    assert abs(sig["payoff_ratio"] - (entry + 6.0 * atr_v - entry)
               / (entry - sig["stop_loss"])) < 1e-9


def test_resolve_target_prefiere_el_target_mas_cercano(engine, ohlcv_df):
    """El target gana el candidato MÁS CERCANO, no el más lejano (RR realista).
    Un FVG bullish cuya mitad inferior está más cerca que la resistencia
    domina, y viceversa."""
    from app.core.signal_engine import _resolve_target
    entry, atr_v = 100.0, 2.0
    ms_fvg_closer = {"fair_value_gap": {"fvg_type": 1, "fvg_bottom": 103.0},
                     "nearest_resistance": 112.0}
    assert abs(_resolve_target(entry, atr_v, ms_fvg_closer) - 103.0) < 1e-9
    ms_res_closer = {"fair_value_gap": {"fvg_type": 1, "fvg_bottom": 109.0},
                     "nearest_resistance": 104.0}
    assert abs(_resolve_target(entry, atr_v, ms_res_closer) - 104.0) < 1e-9
    # FVG por debajo del entry no es candidato de target para un BUY
    ms_fvg_below = {"fair_value_gap": {"fvg_type": 1, "fvg_bottom": 95.0}}
    assert abs(_resolve_target(entry, atr_v, ms_fvg_below)
               - (entry + 4.0 * atr_v)) < 1e-9
    # sin estructura: fallback exacto 4·ATR
    assert abs(_resolve_target(entry, atr_v, None) - (entry + 4.0 * atr_v)) < 1e-9
    assert abs(_resolve_target(entry, atr_v, {}) - (entry + 4.0 * atr_v)) < 1e-9


# --- Fase 0b v2: señal de RANKING G2 (H7-OOS) ---

def _g2_fixture_df(n: int = 300) -> pd.DataFrame:
    """Serie sintética de momentum/rsi para compute_g2_rank_scores (no usa
    OHLCV: la función es vectorizada sobre indicadores ya calculados)."""
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    mom = pd.Series(np.linspace(-20, 80, n), index=idx)
    rsi = pd.Series(np.linspace(35, 75, n), index=idx)
    return pd.DataFrame({"momentum_12_1": mom, "rsi14": rsi}, index=idx)


def test_g2_without_sentiment_is_half_rank(engine):
    df = _g2_fixture_df()
    g2 = engine.compute_g2_rank_scores(df)
    assert g2.between(-1.0, 1.0).all()
    # Monótono en el score: el final (mom alto, rsi alto) debe rankear > 0
    assert g2.iloc[-1] > 0.0
    assert g2.iloc[0] == 0.0  # warmup < 60 obs -> neutro 0.0


def test_g2_sentiment_ranks_spread_causally(engine):
    df = _g2_fixture_df()
    dates = df.index
    # Tendencia a EUFORIA (spread subiendo a +30) vs PESIMISMO (bajando a -30):
    # en el tramo final, la euforia debe rankear s_v1 negativo -> g2 más bajo
    euphoria = {d: 30.0 * i / len(dates) for i, d in enumerate(dates)}
    pessimism = {d: -30.0 * i / len(dates) for i, d in enumerate(dates)}
    g2_euph = engine.compute_g2_rank_scores(df, euphoria)
    g2_pess = engine.compute_g2_rank_scores(df, pessimism)
    # Mismo score técnico -> mismo rank(score); el spread decide la diferencia
    assert g2_pess.iloc[-1] > g2_euph.iloc[-1]
    # El shock final de euforia hunde el g2 respecto del mismo mundo sin shock
    neutral = {d: 0.0 for d in dates[:-1]}
    neutral[dates[-1]] = 30.0
    g2_shock = engine.compute_g2_rank_scores(df, neutral)
    assert g2_shock.iloc[-1] < g2_pess.iloc[-1]
    assert g2_shock.iloc[-1] < 0.0  # el shock rankea s_v1 fuertemente negativo


def test_rank_signals_uses_g2_score_when_present(engine):
    signals = [{"symbol": "A", "score": 0.9, "g2_score": -0.5},
               {"symbol": "B", "score": 0.3, "g2_score": 0.8}]
    ranked = engine.rank_signals(signals)
    assert [s["symbol"] for s in ranked] == ["B", "A"]


def test_rank_signals_backward_compatible_without_g2(engine):
    signals = [{"symbol": "A", "score": 0.3}, {"symbol": "B", "score": 0.9}]
    ranked = engine.rank_signals(signals)
    assert [s["symbol"] for s in ranked] == ["B", "A"]
