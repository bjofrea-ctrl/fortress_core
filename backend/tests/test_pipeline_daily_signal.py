"""Tests del pipeline diario (Frente 2) — herméticos: sin red, sin Alpaca, sin DB.

Foco: definición congelada intacta (eco vs motor), matemática de sizing,
idempotencia por estado, planes compra/venta, ejecución con cliente falso
(incluye camino de error que NO corta el resto) y calendario hábil.
"""
import datetime as dt
import os
from pathlib import Path

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


# --------------------------------------------- checkpoint-inject (gate 08-25)

def test_inyeccion_marca_override_y_no_duplica_senal_genuina():
    reales = [{"symbol": "AAPL", "score": 0.71, "price_ref": 100.0}]
    inyectadas, notas = pl.apply_checkpoint_injection(
        reales, ["AAPL", "TSLA"],
        price_lookup=lambda s: {"score": 0.2, "close": 250.0})
    by = {s["symbol"]: s for s in inyectadas}
    assert len(inyectadas) == 2                      # AAPL no se duplica
    assert "checkpoint_override" not in by["AAPL"]   # genuina queda intacta
    assert by["TSLA"]["checkpoint_override"] is True
    assert by["TSLA"]["price_ref"] == 250.0
    assert any("no se marca override" in n for n in notas)


def test_plan_enter_sid_prefijado_chkpt_para_trades_de_mecanismo():
    state = pl.new_state()
    sized = [{"symbol": "TSLA", "score": 0.2, "price_ref": 250.0, "qty": 4,
              "checkpoint_override": True},
             {"symbol": "MSFT", "score": 0.68, "price_ref": 200.0, "qty": 5}]
    plans = pl.plan_enter(state, "202609", sized, dt.date(2026, 9, 1))
    by = {p["symbol"]: p for p in plans}
    assert by["TSLA"]["sid"].startswith("chkpt__")
    assert by["TSLA"]["checkpoint_override"] is True
    assert not by["MSFT"]["sid"].startswith("chkpt__")
    # y jamas colisionan entre si aunque coincidan simbolo+fecha
    assert by["TSLA"]["sid"] != by["MSFT"]["sid"]


def test_execute_guarda_override_en_estado_y_venta_deja_nota():
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    plans = pl.plan_enter(state, "202609",
                          [{"symbol": "TSLA", "score": 0.2, "price_ref": 250.0,
                            "qty": 4, "checkpoint_override": True}], fecha)
    pl.execute_plans(plans, state, dry_run=False, phase="enter",
                     ref=fecha, client_factory=FakeClient)
    e = state["entries"]["chkpt__TSLA__2026-09-01"]
    assert e["checkpoint_override"] is True and e["status"] == "OPEN"
    exit_plans = pl.plan_exit(state)
    pl.execute_plans(exit_plans, state, dry_run=False, phase="exit",
                     ref=dt.date(2026, 9, 30), client_factory=FakeClient)
    assert state["entries"]["chkpt__TSLA__2026-09-01"]["exit_note"].startswith(
        "OVERRIDE_MECANISMO")


def test_ledger_row_payload_marca_triple_condicion_b():
    entry = {"signal_id": "TSLA__2026-09-01", "symbol": "TSLA",
             "entry_date": "2026-09-01", "exit_date": "2026-09-30",
             "checkpoint_override": True}
    row = pl.ledger_row_payload(entry, exit_reason="MONTH_END", pnl_r=-0.01)
    import json as _json
    assert row["signal_id"].startswith("chkpt__")
    assert row["exit_reason"].startswith("OVERRIDE_MECANISMO")
    assert _json.loads(row["factors_json"]) == {"checkpoint_override": True}
    real = pl.ledger_row_payload({**entry, "checkpoint_override": False,
                                  "signal_id": "AAPL__2026-09-01"},
                                 exit_reason="MONTH_END", pnl_r=0.02)
    assert not real["signal_id"].startswith("chkpt__")
    assert real["exit_reason"] == "MONTH_END"
    assert _json.loads(real["factors_json"]) == {}


# --------------------------------- integración ledger real (merge 838934b)

def test_net_return_r_descuenta_costs_y_cae_en_casos_borde():
    c = 0.0005 + 0.0005
    esperado = ((110 * (1 - c)) / (100 * (1 + c))) - 1
    assert pl._net_return_r(100.0, 110.0) == pytest.approx(esperado, abs=1e-9)
    assert pl._net_return_r(None, 110.0, price_ref=100.0) == pytest.approx(esperado, abs=1e-9)
    assert pl._net_return_r(None, None) == 0.0


def test_plan_enter_capas_skip_ledger_y_broker():
    state = pl.new_state()
    sized = [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 5},
             {"symbol": "MSFT", "score": 0.69, "price_ref": 200.0, "qty": 3},
             {"symbol": "NVDA", "score": 0.68, "price_ref": 300.0, "qty": 2}]
    plans = pl.plan_enter(state, "202609", sized, dt.date(2026, 9, 1),
                          skip_sids={"MSFT__2026-09-01"}, held_symbols={"NVDA"})
    by = {p["symbol"]: p for p in plans}
    assert by["AAPL"]["status"] if False else "qty" in by["AAPL"]   # pasa a compra
    assert by["MSFT"]["skip_reason"] == "ya_abierta_en_ledger"
    assert by["NVDA"]["skip_reason"] == "posicion_existente_en_broker"
    assert "skip_reason" not in by["AAPL"]


def test_execute_con_ledger_real_roundtrip_abre_y_cierra(tmp_path):
    from app.core.signal_ledger import SignalLedger
    led = SignalLedger(db_path=str(tmp_path / "test_ledger.db"))
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)

    class FillClient(FakeClient):
        def submit_market_order(self, symbol, qty, side):
            super().submit_market_order(symbol, qty, side)
            return {"filled_avg_price": 100.0 if side == "buy" else 110.0,
                    "status": "filled"}

    buys = pl.plan_enter(state, "202609",
                         [{"symbol": "AAPL", "score": 0.7, "price_ref": 100.0, "qty": 5}],
                         fecha)
    pl.execute_plans(buys, state, dry_run=False, phase="enter", ref=fecha,
                     client_factory=lambda: FillClient(), ledger=led)
    abiertas = led.open_orders()
    assert len(abiertas) == 1 and abiertas[0]["signal_id"] == "AAPL__2026-09-01"
    assert abiertas[0]["status"] == "open" and abiertas[0]["qty"] == 5

    sells = pl.plan_exit(state) or pl.plan_exit_from_ledger(abiertas)
    pl.execute_plans(sells, state, dry_run=False, phase="exit", ref=dt.date(2026, 9, 30),
                     client_factory=lambda: FillClient(), ledger=led)
    assert led.open_orders() == []
    fila = led.fetch(symbol="AAPL")[0]
    assert fila["status"] == "closed" and fila["exit_reason"] == "MONTH_END"
    assert fila["pnl_r"] == pytest.approx(pl._net_return_r(100.0, 110.0), abs=1e-6)


def test_override_llega_marcado_al_ledger_real_condicion_b(tmp_path):
    from app.core.signal_ledger import SignalLedger
    led = SignalLedger(db_path=str(tmp_path / "test_ledger.db"))
    state = pl.new_state()
    fecha = dt.date(2026, 9, 1)
    buys = pl.plan_enter(state, "202609",
                         [{"symbol": "TSLA", "score": 0.2, "price_ref": 250.0, "qty": 4,
                           "checkpoint_override": True}], fecha)
    pl.execute_plans(buys, state, dry_run=False, phase="enter", ref=fecha,
                     client_factory=FakeClient, ledger=led)
    import json as _json
    row = led.open_orders()[0]
    assert row["signal_id"].startswith("chkpt__")
    assert _json.loads(row["factors_json"]) == {"checkpoint_override": True}
    sells = pl.plan_exit(state)
    pl.execute_plans(sells, state, dry_run=False, phase="exit", ref=dt.date(2026, 9, 30),
                     client_factory=FakeClient, ledger=led)
    cerrada = led.fetch(symbol="TSLA")[0]
    assert cerrada["exit_reason"].startswith("OVERRIDE_MECANISMO")


# -------------------------------------------------------------- calendario

def test_month_bounds_primer_y_ultimo_habil_desde_indice_sintetico():
    days = pd.DatetimeIndex(pd.bdate_range("2026-01-01", "2026-03-10")).normalize().unique().sort_values()
    f_jan, l_jan = pl.month_bounds(days, dt.date(2026, 1, 15))
    _, l_feb = pl.month_bounds(days, dt.date(2026, 2, 10))
    assert f_jan == dt.date(2026, 1, 1)
    assert l_jan.weekday() != 5 and l_jan.weekday() != 6
    assert l_feb == dt.date(2026, 2, 27)  # viernes previo al fin de semana
# ------------------------------------- A1 reconciler (remedio brechas 09-03)
# Condición (c) del gate: las órdenes abiertas del ledger deben tener posición
# real en el paper. reconcile_orphans cierra las huérfanas con pnl_r REAL y
# cuenta las posiciones sin explicación contable; registra en state + log.

class ReconFakeClient(FakeClient):
    """Cliente fake de papel con posiciones y último trade (sin red)."""

    def __init__(self, positions=(), prices=None):
        super().__init__()
        self._positions = list(positions)
        self._prices = dict(prices or {})

    def get_positions(self):
        return [{"symbol": s} for s in self._positions]

    def last_trade_price(self, symbol):
        if symbol not in self._prices:
            raise RuntimeError(f"sin precio para {symbol}")
        return self._prices[symbol]


def _sembrar_ledger(tmp_path, *opens):
    from app.core.signal_ledger import SignalLedger
    led = SignalLedger(db_path=str(tmp_path / "ledger.db"))
    for sid, sym, open_price in opens:
        led.open_order(sid, sym, "2026-08-03", 10, open_price)
    return led


def test_reconcile_cierra_huerfana_con_pnl_r_real_y_registra_en_state_y_log(tmp_path):
    # Ticket A1: 1 orden huérfana -> cerrada con pnl_r REAL != 0.0, línea en
    # pipeline_state.json (state) y en pipeline_diario.log.
    led = _sembrar_ledger(tmp_path, ("ORPH__2026-08-03", "ORPH", 100.0))
    client = ReconFakeClient(positions=[], prices={"ORPH": 110.0})
    state = pl.new_state()
    log = str(tmp_path / "pipeline_diario.log")
    res = pl.reconcile_orphans(led, client, exit_date="2026-09-02",
                               state=state, log_path=log)

    assert res["orphan_closed"] == 1
    assert res["unexplained"] == 0
    fila = led.fetch(symbol="ORPH")[0]
    assert fila["status"] == "closed"
    assert fila["exit_reason"] == "RECONCILE"
    # pnl_r real = (close-open)/open con el último trade, NO 0.0 a ciegas.
    assert fila["pnl_r"] == pytest.approx((110.0 - 100.0) / 100.0, abs=1e-9)
    assert fila["close_fill_price"] == pytest.approx(110.0, abs=1e-9)
    # state: reconcile persistido (el contador A2 lo lee como condición (c)).
    assert state["reconcile"]["orphan_closed"] == 1
    assert state["reconcile"]["unexplained"] == 0
    # log: la métrica está presente en pipeline_diario.log.
    with open(log, encoding="utf-8") as fh:
        texto = fh.read()
    assert "reconcile orphan_closed=1 unexplained=0" in texto


def test_reconcile_no_toca_orden_viva_y_cuenta_posicion_sin_explicar(tmp_path):
    led = _sembrar_ledger(tmp_path, ("SYNC__2026-08-03", "SYNC", 50.0))
    # SYNC tiene posición real (explicada); ZZZ es una posición del paper que el
    # ledger no registra (comprada fuera del sistema) -> unexplained.
    client = ReconFakeClient(positions=["SYNC", "ZZZ"], prices={"SYNC": 55.0})
    log = str(tmp_path / "pipeline_diario.log")
    res = pl.reconcile_orphans(led, client, exit_date="2026-09-02", log_path=log)
    assert res["orphan_closed"] == 0
    assert res["unexplained"] == 1
    assert res["unexplained_symbols"] == ["ZZZ"]
    assert [r["signal_id"] for r in led.open_orders()] == ["SYNC__2026-08-03"]


def test_reconcile_idempotente_no_recuenta_la_misma_huerfana(tmp_path):
    led = _sembrar_ledger(tmp_path, ("ORPH__2026-08-03", "ORPH", 100.0))
    client = ReconFakeClient(positions=[], prices={"ORPH": 110.0})
    log = str(tmp_path / "pipeline_diario.log")
    primera = pl.reconcile_orphans(led, client, exit_date="2026-09-02", log_path=log)
    segunda = pl.reconcile_orphans(led, client, exit_date="2026-09-03", log_path=log)
    assert primera["orphan_closed"] == 1
    assert segunda["orphan_closed"] == 0   # ya cerrada -> no se re-cuenta
    assert len(led.fetch(symbol="ORPH")) == 1  # la fila se cerró, no se duplicó


def test_reconcile_sin_precio_cierra_con_0_visible_y_no_lanza(tmp_path):
    led = _sembrar_ledger(tmp_path, ("ORPH__2026-08-03", "ORPH", 100.0))
    client = ReconFakeClient(positions=[], prices={})  # last_trade_price falla
    log = str(tmp_path / "pipeline_diario.log")
    res = pl.reconcile_orphans(led, client, exit_date="2026-09-02", log_path=log)
    assert res["orphan_closed"] == 1
    assert res["sin_precio"] == 1   # el fallo de precio queda visible, no oculto
    fila = led.fetch(symbol="ORPH")[0]
    assert fila["status"] == "closed" and fila["pnl_r"] == 0.0


def test_reconcile_dia_limpio_sin_huerfanas_ni_inexplicadas(tmp_path):
    led = _sembrar_ledger(tmp_path, ("SYNC__2026-08-03", "SYNC", 50.0))
    client = ReconFakeClient(positions=["SYNC"], prices={"SYNC": 55.0})
    log = str(tmp_path / "pipeline_diario.log")
    res = pl.reconcile_orphans(led, client, exit_date="2026-09-02", log_path=log)
    assert res == {"orphan_closed": 0, "unexplained": 0,
                   "unexplained_symbols": [], "sin_precio": 0,
                   "exit_date": "2026-09-02", "timestamp": res["timestamp"]}
    assert [r["signal_id"] for r in led.open_orders()] == ["SYNC__2026-08-03"]


def test_reconcile_escribe_al_log_canonico_scripts_del_repo(tmp_path):
    # A1 regresión: DIARIO_LOG debe apuntar al log canónico que la shell
    # redirige (scripts/pipeline_diario.log en la RAÍZ del repo, no a
    # backend/scripts/). Es el archivo que A2 va a parsear para la condición
    # (c). El módulo corre con cwd=backend (daily_signal_pipeline.sh hace
    # cd $REPO/backend, igual que estos tests), así que el default de
    # reconcile_orphans (log_path=DIARIO_LOG) resuelve a <raíz>/scripts/.
    repo_root = Path(__file__).resolve().parents[2]
    canonico = repo_root / "scripts" / "pipeline_diario.log"

    # El path NO es backend/scripts/ (bug reportado: __file__ resuelve ahí).
    assert os.path.abspath(pl.DIARIO_LOG) != str(
        Path(__file__).resolve().parents[1] / "scripts" / "pipeline_diario.log"
    )
    # Y SÍ es scripts/pipeline_diario.log relativo a la raíz del repo.
    assert os.path.normpath(os.path.abspath(pl.DIARIO_LOG)) == os.path.normpath(
        str(canonico)
    )

    # La línea de reconcile cae AHÍ usando el default (sin log_path override).
    led = _sembrar_ledger(tmp_path, ("ORPH__2026-08-03", "ORPH", 100.0))
    client = ReconFakeClient(positions=[], prices={"ORPH": 110.0})
    pl.reconcile_orphans(led, client, exit_date="2026-09-02")
    assert canonico.exists()
    with open(canonico, encoding="utf-8") as fh:
        assert "reconcile orphan_closed=1 unexplained=0" in fh.read()
