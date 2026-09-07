"""B8 §2b — tests del cap de sizing fractional-Kelly en AdaptiveRiskManager.

Cubre:
  - edge insuficiente (2a dijo "n insuficiente") => default conservador, no Kelly simulación.
  - edge negativo => cap nunca negativo (no se aplica Kelly negativo a ciegas).
  - edge positivo => cap == fórmula Kelly fraccionario combinada (mínimo) con max_exposure.
  - cap acotado por max_exposure del régimen.
  - effective_risk_per_trade nunca excede el RISK_PER_TRADE fijo (techo de crecimiento).
  - compute_position_size respeta el edge medido (sin regresión cuando no se pasa).
"""
import pytest
from app.config import settings
from app.core.adaptive_risk import (
    DEFAULT_KELLY_FRACTION,
    AdaptiveRiskManager,
    get_regime_thresholds,
)


@pytest.fixture
def rm():
    return AdaptiveRiskManager(initial_equity=25000)


def _kelly_full(win_rate: float, reward_risk: float) -> float:
    return max(0.0, win_rate * reward_risk - (1 - win_rate)) / reward_risk


def test_cap_insufficient_returns_conservative_default(rm):
    # 2a devolvió "n insuficiente": win_rate=None / reward_risk=None.
    cap = rm.risk_per_trade_cap(None, None, regime_state=0)
    expected = min(settings.RISK_PER_TRADE, get_regime_thresholds(0)["max_exposure"])
    assert cap == pytest.approx(expected)


def test_cap_negative_edge_never_negative(rm):
    # Edge negativo (win 0.3, RR 0.5 => Kelly < 0) => default conservador, jamás negativo.
    cap = rm.risk_per_trade_cap(0.3, 0.5, regime_state=0)
    expected = min(settings.RISK_PER_TRADE, get_regime_thresholds(0)["max_exposure"])
    assert cap == pytest.approx(expected)
    assert cap >= 0.0


def test_cap_positive_edge_matches_kelly_formula(rm):
    wr, rr = 0.4, 2.0
    expected = min(
        _kelly_full(wr, rr) * DEFAULT_KELLY_FRACTION,
        get_regime_thresholds(0)["max_exposure"],
    )
    assert rm.risk_per_trade_cap(wr, rr, regime_state=0) == pytest.approx(expected)


def test_cap_bounded_by_regime_max_exposure(rm):
    # Régimen 3: max_exposure=0.20; un edge fuerte no debe excederlo.
    cap = rm.risk_per_trade_cap(0.6, 3.0, regime_state=3)
    regime_cap = get_regime_thresholds(3)["max_exposure"]
    assert cap <= regime_cap + 1e-12
    assert cap == pytest.approx(min(_kelly_full(0.6, 3.0) * DEFAULT_KELLY_FRACTION, regime_cap))


def test_effective_risk_never_exceeds_fixed(rm):
    # El efectivo siempre es <= RISK_PER_TRADE fijo (es un techo de crecimiento).
    for wr, rr, reg in [(0.4, 2.0, 0), (0.6, 3.0, 0), (None, None, 0), (0.3, 0.5, 0)]:
        eff = rm.effective_risk_per_trade(wr, rr, regime_state=reg)
        assert 0.0 <= eff <= settings.RISK_PER_TRADE + 1e-12


def test_positive_edge_cap_lowers_below_fixed_when_weak(rm):
    # Edge débil => cap por debajo del fijo => acota el crecimiento.
    eff_weak = rm.effective_risk_per_trade(0.5, 1.1, regime_state=0)
    assert eff_weak < settings.RISK_PER_TRADE
    # Edge fuerte => cap alto => rige el fijo (no crece por encima de 1.5%).
    eff_strong = rm.effective_risk_per_trade(0.9, 5.0, regime_state=0)
    assert eff_strong == pytest.approx(settings.RISK_PER_TRADE)


def test_compute_position_size_uses_measured_edge_when_provided(rm):
    rm.update_regime(0)
    rm.MAX_POSITION_PCT = 10.0  # fuerza que rija risk_per_trade, no el cap de posición
    base = rm.compute_position_size(25000, 100, 2.0)  # riesgo fijo 1.5% => 75 shares (stop=5)
    # Edge débil (cap Kelly < 1.5%) reduce el riesgo => menos shares.
    weak = rm.compute_position_size(
        25000, 100, 2.0, measured_win_rate=0.5, measured_reward_risk=1.1
    )
    assert weak < base
    # Sin edge medido => comportamiento original (no regresión).
    assert base == rm.compute_position_size(25000, 100, 2.0)


def test_compute_position_size_insufficient_edge_no_regression(rm):
    rm.update_regime(0)
    rm.MAX_POSITION_PCT = 10.0
    base = rm.compute_position_size(25000, 100, 2.0)
    insuff = rm.compute_position_size(
        25000, 100, 2.0, measured_win_rate=None, measured_reward_risk=None
    )
    assert insuff == base
