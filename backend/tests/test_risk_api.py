"""Tests de integración del router /api/risk (SQLAlchemy).

No se toca la BD real: se monkeypatchea risk.SessionLocal con un stub que
emula la cadena query().order_by().first() / query().filter().count().
"""
import asyncio

from app.api.routes import risk
from app.models.database import PortfolioSnapshot, RiskEvent


class _StubQuery:
    def __init__(self, result):
        self._result = result

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._result

    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return self._result


class _StubSession:
    def __init__(self, snapshot, violations):
        self._snapshot = snapshot
        self._violations = violations

    def query(self, model):
        if model is PortfolioSnapshot:
            return _StubQuery(self._snapshot)
        if model is RiskEvent:
            return _StubQuery(self._violations)
        raise AssertionError(f"query() inesperado para {model}")


def _patch(monkeypatch, session):
    monkeypatch.setattr(risk, "SessionLocal", lambda: session)


def test_monitor_sin_datos(monkeypatch):
    _patch(monkeypatch, _StubSession(snapshot=None, violations=0))
    body = asyncio.run(risk.risk_monitor(db=_StubSession(None, 0)))
    assert body["status"] == "no_data"
    assert "absolute_ceiling" in body


def test_monitor_con_datos(monkeypatch):
    snap = PortfolioSnapshot(equity=100000.5, drawdown_pct=-3.2,
                             regime_state=1, num_positions=4)
    session = _StubSession(snapshot=snap, violations=2)
    _patch(monkeypatch, session)
    body = asyncio.run(risk.risk_monitor(db=session))

    assert body["current_equity"] == 100000.5
    assert body["current_drawdown_pct"] == -3.2
    assert body["regime_state"] == 1
    assert body["num_positions"] == 4
    assert body["violations_60d"] == 2
