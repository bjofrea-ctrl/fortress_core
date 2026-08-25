"""Tests del pipeline diario (Frente 2) — herméticos: sin red, sin Alpaca, sin DB.

Foco: definición congelada intacta (eco vs motor), matemática de sizing,
idempotencia por estado, planes compra/venta, ejecución con cliente falso
(incluye camino de error que NO corta el resto) y calendario hábil.
"""
import datetime as dt

import pandas as pd
import pytest
from app.core.signal_engine import SignalEngine

from scripts import pipeline_daily_signal as pl

# ---------------------------------------------------------------- helpers

def _ind_frame(**last_overrides):
    """Frame de indicadores sintético (columnas exactas de compute_factor_frame)."""
    n = 10
    idx = pd.bdate_range("2026-07-01", periods=n)
    base = {
        "close": [100.0] * n,
        "ema50": [95.0] * n,
        "ema200": [90.0] * n,
        "adx14": [25.0] * n,
        "rsi14": [55.0] * n,
        "volume_ratio": [1.2] * n,
        "momentum_12_1": [30.0] * n,
    }
    for k, v in last_overrides.items():
        base[k][-1] = v
    return pd.DataFrame(base, index=idx)


@pytest.fixture()
def eng():
    return SignalEngine(regime_classifier=None)


# ---------------------------------------------------- definición congelada

def test_frozen_echo_pesos_son_los_del_motor_en_runtime(eng):
    echo = pl.frozen_echo()
    w = eng.factor_weights[0]
    assert echo["w_mom_runtime"] == w["momentum"] == 0.6642
    assert echo["w_rsi_runtime"] == w["rsi"] == 0.3358
    assert echo["entry_threshold"] == 0.60
    assert echo["rsi_gate"] == [40, 75] and echo["adx_min"] == 20 and echo["vr_min"] == 1.0


def test_latest_signal_pasa_gates_y_umbral_con_definicion_congelada(eng):
    sig = pl.latest_signal(eng, _ind_frame())
    # score = 0.6642*((30+50)/150) + 0.3358*0.8 = 0.6229 >= 0.60, gates OK
    assert sig["eligible"] is True
    assert round(sig["score"], 4) == 0.6229
    assert sig["close"] == 100.0


def test_latest_signal_gate_adx_fallando_no_es_elegible_aun_con_score_alto(eng):
    sig = pl.latest_signal(eng, _ind_frame(adx14=15.0))
    assert sig["eligible"] is False  # gate duro manda aunque score >= umbral


# ------------------------------------------------------------------ sizing

def test_sizing_floor_equal_weight():
    sized = pl.sizing([{"symbol": "A", "score": 0.7, "price_ref": 300.0},
                       {"symbol": "B", "score": 0.65, "price_ref": 150.0},
                       {"symbol": "C", "score": 0.62, "price_ref": 4000.0}], budget=10000.0)
    by = {o["symbol"]: o for o in sized}
    assert by["A"]["qty"] == 11          # floor(3333.33/300)
    assert by["B"]["qty"] == 22          # floor(3333.33/150)
    assert "C" not in by                 # qty 0 -> filtrado (no fracciones)


def test_client_order_id_determinista_por_mes_y_simbolo():
    a = pl.client_order_id("enter", dt.date(2026, 9, 1), "AAPL")
    b = pl.client_order_id("enter", dt.date(2026, 9, 18), "AAPL")
    c = pl.client_order_id("exit", dt.date(2026, 9, 1), "AAPL")
    assert a == b == "fc-enter-202609-AAPL"   # estable dentro del mes -> re-run seguro
    assert c != a


# --------------------------------------------- planes e idempotencia estado

def test_plan_enter_salta_signal_ids_ya_registrados():
    fecha = dt.date(2026, 9, 1)
    state = pl.new_state()
    state["entries"][f"AAPL__{fecha.isoformat()}"] = {"symbol": "AAPL", "status": "OPEN"}
    sized = [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 10},
             {"symbol": "MSFT", "score": 0.68, "price_ref": 200.0, "qty": 5}]
    plans = pl.plan_enter(state, "202609", sized, fecha)
    by = {p["symbol"]: p for p in plans}
    assert by["AAPL"]["skip_reason"] == "ya_registrado_en_estado"
    assert "qty" not in by["AAPL"]
    assert by["MSFT"]["qty"] == 5 and "skip_reason" not in by["MSFT"]


def test_plan_exit_solo_posiciones_abiertas_del_pipeline():
    state = pl.new_state()
    state["entries"] = {
        "AAPL__2026-09-01": {"symbol": "AAPL", "status": "OPEN", "qty": 10},
        "MSFT__2026-08-03": {"symbol": "MSFT", "status": "CLOSED", "qty": 4},
        "NVDA__2026-09-01": {"symbol": "NVDA", "status": "ERROR"},
    }
    plans = pl.plan_exit(state)
    assert [(p["symbol"], p["qty"]) for p in plans] == [("AAPL", 10)]


class FakeClient:
    def __init__(self, fail_symbols=()):
        self.calls = []
        self.fail_symbols = set(fail_symbols)

    def submit_market_order(self, symbol, qty, side):
        self.calls.append((symbol, qty, side))
        if symbol in self.fail_symbols:
            raise RuntimeError("simulated reject")
        return {"filled_avg_price": 111.0, "status": "filled"}


def test_execute_real_compra_registra_open_y_error_no_corta_el_resto():
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "BAD", "score": 0.7, "price_ref": 50.0, "qty": 2},
                           {"symbol": "GOOD", "score": 0.69, "price_ref": 100.0, "qty": 3}],
                          fecha)
    fake = FakeClient(fail_symbols={"BAD"})
    results = pl.execute_plans(plans, state, dry_run=False, phase="enter",
                               ref=fecha, client_factory=lambda: fake)
    st = {r["symbol"]: r.get("status") for r in results}
    assert st["BAD"] == "error" and st["GOOD"] == "submitted"
    assert state["entries"]["GOOD__2026-09-01"]["status"] == "OPEN"
    assert state["entries"]["GOOD__2026-09-01"]["buy_fill"] == 111.0
    assert state["entries"]["BAD__2026-09-01"]["status"] == "ERROR"


def test_execute_venta_cierra_posicion_y_registra_fill():
    state = pl.new_state()
    state["entries"]["AAPL__2026-09-01"] = {"symbol": "AAPL", "status": "OPEN", "qty": 10}
    plans = pl.plan_exit(state)
    fake = FakeClient()
    results = pl.execute_plans(plans, state, dry_run=False, phase="exit",
                               ref=dt.date(2026, 9, 30), client_factory=lambda: fake)
    assert results[0]["status"] == "submitted" and results[0]["fill"] == 111.0
    e = state["entries"]["AAPL__2026-09-01"]
    assert e["status"] == "CLOSED" and e["sell_fill"] == 111.0
    assert fake.calls == [("AAPL", 10, "sell")]


def test_execute_dry_run_nunca_construye_cliente():
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 5}],
                          fecha)

    def boom():  # si se invoca, el test explota
        raise AssertionError("dry-run no debe construir cliente")

    results = pl.execute_plans(plans, state, dry_run=True, phase="enter",
                               ref=fecha, client_factory=boom)
    assert results[0]["status"] == "dry_run_plan"
    assert state["entries"] == {}  # sin mutación de estado en dry-run


# -------------------------------------------------------------- calendario

def test_month_bounds_primer_y_ultimo_habil_desde_indice_sintetico():
    days = pd.DatetimeIndex(pd.bdate_range("2026-01-01", "2026-03-10")).normalize().unique().sort_values()
    f_jan, l_jan = pl.month_bounds(days, dt.date(2026, 1, 15))
    _, l_feb = pl.month_bounds(days, dt.date(2026, 2, 10))
    assert f_jan == dt.date(2026, 1, 1)
    assert l_jan.weekday() != 5 and l_jan.weekday() != 6
    assert l_feb == dt.date(2026, 2, 27)  # viernes previo al fin de semana
