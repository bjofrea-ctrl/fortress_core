"""Tests A5 — telemetría de ejecución por orden (PLAN_REMEDIO_BRECHAS_20260903).

Cubre: INSERT append-only por orden enviada (buy y sell), slippage correcto,
orden fallida registrada con status=error, dry_run NO registra, separación
checkpoint/oficial, y el hook en execute_plans con el FakeClient existente.
Todo contra tmp_path — jamás fortress.db real ni red.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pipeline_daily_signal as pl  # noqa: E402
from app.core.execution_telemetry import ExecutionTelemetry, compute_slippage  # noqa: E402


class FakeClient:
    def __init__(self, fail_symbols=(), last_trade=100.0):
        self.calls = []
        self.fail_symbols = set(fail_symbols)
        self.last_trade = last_trade

    def submit_market_order(self, symbol, qty, side):
        self.calls.append((symbol, qty, side))
        if symbol in self.fail_symbols:
            raise RuntimeError("simulated reject")
        return {"filled_avg_price": 111.0, "status": "filled"}

    def last_trade_price(self, symbol):
        return self.last_trade


# ------------------------------------------------------------ compute_slippage

def test_compute_slippage_formula():
    assert compute_slippage(100.0, 100.10) == pytest.approx(0.001)
    assert compute_slippage(100.0, 99.90) == pytest.approx(-0.001)
    assert compute_slippage(50.0, 50.0) == 0.0


def test_compute_slippage_none_si_falta_dato_o_decision_invalida():
    assert compute_slippage(None, 100.0) is None
    assert compute_slippage(100.0, None) is None
    assert compute_slippage(0.0, 100.0) is None
    assert compute_slippage(-1.0, 100.0) is None


# -------------------------------------------------------------------- tabla

def test_record_inserta_fila_append_only(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    t.record(phase="enter", run_ref="2026-09-01", symbol="AAPL", side="buy",
             qty=5, decision_price=100.0, fill_price=100.2)
    t.record(phase="enter", run_ref="2026-09-01", symbol="MSFT", side="buy",
             qty=3, decision_price=200.0, fill_price=200.3)
    rows = t.fetch()
    assert len(rows) == 2
    r = rows[0]
    assert r["symbol"] == "AAPL" and r["side"] == "buy" and r["qty"] == 5
    assert r["decision_price"] == 100.0 and r["fill_price"] == 100.2
    assert r["slippage_implicit"] == pytest.approx(0.002)
    assert r["status"] == "submitted" and r["checkpoint_override"] == 0


def test_record_error_queda_con_fill_null_y_status_error(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    t.record(phase="enter", run_ref="2026-09-01", symbol="BAD", side="buy",
             qty=2, decision_price=50.0, fill_price=None, status="error",
             error="simulated reject")
    rows = t.fetch()
    assert rows[0]["status"] == "error"
    assert rows[0]["fill_price"] is None
    assert rows[0]["slippage_implicit"] is None  # sin fill no hay slippage
    assert rows[0]["error"] == "simulated reject"


def test_fetch_only_official_excluye_checkpoint(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    t.record(phase="enter", run_ref="2026-09-01", symbol="AAPL", side="buy",
             qty=5, decision_price=100.0, fill_price=100.2)
    t.record(phase="enter", run_ref="2026-09-01", symbol="TSLA", side="buy",
             qty=4, decision_price=250.0, fill_price=250.5,
             checkpoint_override=True)
    assert t.count() == 2
    assert t.count(only_official=True) == 1
    official = t.fetch(only_official=True)
    assert [r["symbol"] for r in official] == ["AAPL"]


# ------------------------------------------------- hook en execute_plans (A5)

def test_execute_buy_registra_telemetria_con_slippage(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 5}],
                          fecha)
    fake = FakeClient()  # fill 111.0
    results = pl.execute_plans(plans, state, dry_run=False, phase="enter",
                               ref=fecha, client_factory=lambda: fake, telemetry=t)
    rows = t.fetch()
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "AAPL" and r["side"] == "buy" and r["qty"] == 5
    assert r["phase"] == "enter" and r["run_ref"] == "2026-09-01"
    assert r["decision_price"] == 100.0 and r["fill_price"] == 111.0
    assert r["slippage_implicit"] == pytest.approx((111.0 - 100.0) / 100.0)
    # el dict res también lleva los campos (evidencia del artefacto del run)
    assert results[0]["decision_price"] == 100.0
    assert results[0]["slippage_implicit"] == pytest.approx(0.11)


def test_execute_sell_registra_telemetria_con_last_trade(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    state = pl.new_state()
    state["entries"]["AAPL__2026-08-03"] = {"symbol": "AAPL", "status": "OPEN", "qty": 10}
    plans = pl.plan_exit(state)
    # decision del sell = last_trade_price (110.0), fill del FakeClient = 111.0
    fake = FakeClient(last_trade=110.0)
    pl.execute_plans(plans, state, dry_run=False, phase="exit",
                     ref=dt.date(2026, 8, 31), client_factory=lambda: fake, telemetry=t)
    rows = t.fetch()
    assert len(rows) == 1
    r = rows[0]
    assert r["side"] == "sell" and r["phase"] == "exit"
    assert r["decision_price"] == 110.0 and r["fill_price"] == 111.0
    assert r["slippage_implicit"] == pytest.approx(1.0 / 110.0)


def test_execute_sell_sin_last_trade_degrada_a_decision_null(tmp_path):
    """Cliente sin last_trade_price (como el FakeClient original): la venta
    NO falla, la fila queda con decision/fill parcial y slippage NULL."""
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    state = pl.new_state()
    state["entries"]["AAPL__2026-08-03"] = {"symbol": "AAPL", "status": "OPEN", "qty": 10}
    plans = pl.plan_exit(state)

    class NoQuoteClient(FakeClient):
        def last_trade_price(self, symbol):
            raise RuntimeError("quote unavailable")

    pl.execute_plans(plans, state, dry_run=False, phase="exit",
                     ref=dt.date(2026, 8, 31),
                     client_factory=lambda: NoQuoteClient(), telemetry=t)
    rows = t.fetch()
    assert len(rows) == 1
    assert rows[0]["decision_price"] is None
    assert rows[0]["fill_price"] == 111.0
    assert rows[0]["slippage_implicit"] is None


def test_execute_orden_fallida_registra_error_en_telemetria(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "BAD", "score": 0.7, "price_ref": 50.0, "qty": 2}],
                          fecha)
    fake = FakeClient(fail_symbols={"BAD"})
    pl.execute_plans(plans, state, dry_run=False, phase="enter",
                     ref=fecha, client_factory=lambda: fake, telemetry=t)
    rows = t.fetch()
    assert len(rows) == 1
    assert rows[0]["status"] == "error"
    assert rows[0]["fill_price"] is None
    assert rows[0]["decision_price"] == 50.0  # el precio de decisión sí existía


def test_execute_dry_run_no_registra_telemetria(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 5}],
                          fecha)

    def boom():
        raise AssertionError("dry-run no debe construir cliente")

    pl.execute_plans(plans, state, dry_run=True, phase="enter",
                     ref=fecha, client_factory=boom, telemetry=t)
    assert t.count() == 0  # sin orden real no hay evento que medir


def test_execute_sin_telemetry_comporta_igual_que_antes(tmp_path):
    """Retrocompatibilidad: no pasar telemetry no rompe nada (backwards)."""
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 5}],
                          fecha)
    results = pl.execute_plans(plans, state, dry_run=False, phase="enter",
                               ref=fecha, client_factory=lambda: FakeClient())
    assert results[0]["status"] == "submitted"
    assert "decision_price" not in results[0]  # sin telemetry no agrega campos


def test_execute_checkpoint_override_marcado_en_telemetria(tmp_path):
    t = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "TSLA", "score": 0.2, "price_ref": 250.0, "qty": 4,
                            "checkpoint_override": True}], fecha)
    pl.execute_plans(plans, state, dry_run=False, phase="enter",
                     ref=fecha, client_factory=lambda: FakeClient(), telemetry=t)
    rows = t.fetch()
    assert rows[0]["checkpoint_override"] == 1
    assert t.fetch(only_official=True) == []  # mecanismo jamás en el libro oficial
