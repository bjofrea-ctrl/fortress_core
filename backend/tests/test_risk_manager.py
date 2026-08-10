import pytest

from app.core.adaptive_risk import AdaptiveRiskManager


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
