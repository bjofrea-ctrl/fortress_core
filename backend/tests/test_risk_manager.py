import datetime

import pytest
from app.core.adaptive_risk import AdaptiveRiskManager

D = datetime.datetime(2026, 8, 10)


@pytest.fixture
def rm():
    return AdaptiveRiskManager(initial_equity=25000)


def _force_regime(rm, state):
    rm.update_regime(state)


def _reasons(rm, equity, prices, atrs, date):
    out = {}
    for sym, reason in rm.check_all_stops(equity, prices, atrs, date):
        out.setdefault(sym, []).append(reason)
    return out


def test_partial_tp_fires_only_once_per_position(rm):
    rm.register_entry("AAPL", entry_price=100.0, shares=100)
    atr = 2.0  # 2*atr = 4 -> umbral +2ATR = 104

    _force_regime(rm, 0)

    day1 = _reasons(rm, 25000, {"AAPL": 110.0}, {"AAPL": atr}, None)
    assert day1.get("AAPL") == ["PARTIAL_TP"], "debe disparar el primer parcial sobre +2ATR"

    day2 = _reasons(rm, 25000, {"AAPL": 115.0}, {"AAPL": atr}, None)
    assert "AAPL" not in day2, "no debe re-disparar PARTIAL_TP mientras siga sobre +2ATR"

    day3 = _reasons(rm, 25000, {"AAPL": 120.0}, {"AAPL": atr}, None)
    assert "AAPL" not in day3, "no debe re-disparar PARTIAL_TP en días sucesivos"


def test_partial_done_resets_after_full_exit(rm):
    rm.register_entry("AAPL", entry_price=100.0, shares=100)
    atr = 2.0

    _force_regime(rm, 0)

    to_close = _reasons(rm, 25000, {"AAPL": 110.0}, {"AAPL": atr}, None)
    assert to_close.get("AAPL") == ["PARTIAL_TP"]

    # venta del parcial: quedan 50
    rm.register_exit("AAPL", 50)
    # el resto se cierra con salida técnica
    rm.register_exit("AAPL", 50)

    # re-entrada limpia: el flag debe estar reseteado
    rm.register_entry("AAPL", entry_price=90.0, shares=100)
    to_close = _reasons(rm, 25000, {"AAPL": 99.0}, {"AAPL": atr}, None)
    assert to_close.get("AAPL") == ["PARTIAL_TP"], "tras salir completo, el parcial debe volver a disparar"


def test_no_partial_below_2atr(rm):
    rm.register_entry("AAPL", entry_price=100.0, shares=100)
    _force_regime(rm, 0)
    to_close = _reasons(rm, 25000, {"AAPL": 103.0}, {"AAPL": 2.0}, None)
    assert "AAPL" not in to_close, "por debajo de +2ATR no hay parcial"


def test_no_cooldown_lock_without_positions(rm):
    """Bug del lock permanente: con dd <= -5% pero SIN posiciones, el motor
    rearmaba cooldown y logueaba violación TODOS los días, bloqueando las
    entradas para siempre. Ahora: sin posiciones, sin cooldown, sin violación."""
    _force_regime(rm, 0)
    rm.update_peak(25000.0)
    equity_in_dd = 23500.0  # dd = -6% <= portfolio_stop 5%
    events_before = len(rm.state.risk_events)
    reasons = _reasons(rm, equity_in_dd, {}, {}, D)
    assert reasons == {}, "sin posiciones no debe liquidar nada"
    assert rm.state.cooldown_until is None, "sin posiciones no debe rearmar cooldown"
    assert len(rm.state.risk_events) == events_before, "sin posiciones no debe loguear violación"
    assert rm.can_open_new_position(D) is True, "debe poder re-entrar"


def test_cooldown_still_fires_with_positions_in_drawdown(rm):
    _force_regime(rm, 0)
    rm.update_peak(25000.0)
    rm.register_entry("AAPL", entry_price=100.0, shares=100)
    reasons = _reasons(rm, 23500.0, {"AAPL": 100.0}, {"AAPL": 2.0}, D)
    assert reasons.get("AAPL") == ["PORTFOLIO_REGIME_STOP"], "con posiciones el stop de cartera sigue"
    assert rm.state.cooldown_until is not None, "con posiciones el cooldown sigue disparando"
    assert rm.can_open_new_position(D) is False
