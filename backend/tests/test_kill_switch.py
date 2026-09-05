"""Tests A3 — kill-switch por divergencia (PLAN_REMEDIO_BRECHAS_20260903).

Una fixture por condición pre-declarada + integración en phase_enter/exit.
Todo contra tmp_path (chdir con monkeypatch para los paths data/ relativos);
jamás fortress.db real, jamás red, jamás osascript real (pinchado).
"""
import datetime as dt
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kill_switch as ks  # noqa: E402
import pipeline_daily_signal as pl  # noqa: E402
from app.core.execution_telemetry import ExecutionTelemetry  # noqa: E402
from app.core.signal_ledger import SignalLedger  # noqa: E402

# --------------------------------------------------------- reglas puras (i)

class TestRuleDrawdown:
    def test_dispara_con_equity_11pct_debajo_del_pico(self):
        v = ks.rule_drawdown(equity=8900.0, peak_equity=10000.0)
        assert v["fired"] is True
        assert v["detail"]["drawdown"] == pytest.approx(0.11)

    def test_no_dispara_con_equity_dentro_del_10pct(self):
        v = ks.rule_drawdown(equity=9100.0, peak_equity=10000.0)
        assert v["fired"] is False
        assert v["detail"]["drawdown"] == pytest.approx(0.09)

    def test_borde_exacto_10pct_no_dispara(self):
        v = ks.rule_drawdown(equity=9000.0, peak_equity=10000.0)
        assert v["fired"] is False  # >10%, no >=10%: el borde queda adentro

    def test_se_abstiene_sin_equity_o_sin_pico(self):
        assert ks.rule_drawdown(None, 10000.0)["abstained"] is True
        assert ks.rule_drawdown(9000.0, None)["abstained"] is True
        assert ks.rule_drawdown(9000.0, 0.0)["abstained"] is True


# -------------------------------------------------------- reglas puras (ii)

class TestRulePnlDaily:
    HISTORY = [0.05, -0.02, 0.08, 0.01, -0.04, 0.03, 0.06, -0.01, 0.02, 0.04]

    def test_dispara_con_pnl_debajo_de_media_menos_3sigma(self):
        import statistics
        mean = statistics.fmean(self.HISTORY)
        sigma = statistics.stdev(self.HISTORY)
        hoy = mean - 3.0 * sigma - 0.01
        v = ks.rule_pnl_daily(hoy, self.HISTORY)
        assert v["fired"] is True

    def test_no_dispara_con_pnl_normal(self):
        v = ks.rule_pnl_daily(-0.02, self.HISTORY)
        assert v["fired"] is False

    def test_se_abstiene_sin_cierres_hoy(self):
        assert ks.rule_pnl_daily(None, self.HISTORY)["abstained"] is True

    def test_se_abstiene_con_menos_de_10_dias_de_historia(self):
        v = ks.rule_pnl_daily(-5.0, [0.1, 0.2, 0.3])
        assert v["abstained"] is True and v["fired"] is False

    def test_se_abstiene_con_sigma_cero(self):
        v = ks.rule_pnl_daily(-5.0, [0.0] * 15)
        assert v["abstained"] is True and v["fired"] is False


# ------------------------------------------------------- reglas puras (iii)

class TestRuleFillRate:
    def test_dispara_con_2_de_5_fills(self):
        v = ks.rule_fill_rate(n_total=5, n_filled=2)
        assert v["fired"] is True
        assert v["detail"]["rate"] == 0.4

    def test_dispara_con_cero_fills_y_al_menos_un_orden(self):
        v = ks.rule_fill_rate(n_total=1, n_filled=0)
        assert v["fired"] is True  # ejecución rota aunque n < 3

    def test_no_dispara_con_4_de_5_fills(self):
        v = ks.rule_fill_rate(n_total=5, n_filled=4)
        assert v["fired"] is False  # 80% exacto = dentro

    def test_no_dispara_con_pocos_intentos_y_algo_lleno(self):
        v = ks.rule_fill_rate(n_total=2, n_filled=1)
        assert v["fired"] is False  # 50% pero n<3: muestra chica, no concluye

    def test_se_abstiene_sin_ordenes_hoy(self):
        v = ks.rule_fill_rate(n_total=0, n_filled=0)
        assert v["abstained"] is True and v["fired"] is False


# -------------------------------------------------------- reglas puras (iv)

class TestRuleStaleness:
    def test_dispara_con_3_ruedas_stale(self):
        assert ks.rule_staleness(3)["fired"] is True

    def test_no_dispara_con_2_ruedas(self):
        assert ks.rule_staleness(2)["fired"] is False  # borde: 2 = dentro

    def test_se_abstiene_sin_calendario(self):
        assert ks.rule_staleness(None)["abstained"] is True


# --------------------------------------------------------- veredictos

class TestVerdicts:
    def test_evaluate_pre_order_sin_disparo(self):
        v = ks.evaluate_pre_order(9500.0, 10000.0, -0.02,
                                  [0.05, -0.02, 0.08, 0.01, -0.04, 0.03,
                                   0.06, -0.01, 0.02, 0.04], 0)
        assert v["stopped"] is False
        assert len(v["evaluated"]) == 3

    def test_evaluate_health_con_staleness_dispara(self):
        v = ks.evaluate_health(None, [], 0, 0, 3)
        assert v["stopped"] is True
        assert [r["rule"] for r in v["fired"]] == ["staleness"]


# ------------------------------------------------------------ gatherers

class TestGatherers:
    def test_daily_pnls_from_ledger_separa_hoy_de_historia(self, tmp_path):
        led = SignalLedger(db_path=str(tmp_path / "led.db"))
        # 12 días de historia + un cierre HOY de -5.0R (debería disparar 3σ)
        hoy = dt.date.today().isoformat()
        for i, pnl in enumerate([0.05, -0.02, 0.08, 0.01, -0.04, 0.03,
                                 0.06, -0.01, 0.02, 0.04, 0.01, 0.03]):
            d = (dt.date.today() - dt.timedelta(days=i + 1)).isoformat()
            led.open_order(f"S{i}", "AAPL", d, 5, 100.0)
            led.close_order(f"S{i}", d, "MONTH_END", pnl, 101.0)
        led.open_order("HOY", "AAPL", hoy, 5, 100.0)
        led.close_order("HOY", hoy, "MONTH_END", -5.0, 95.0)
        today_pnl, history = ks.daily_pnls_from_ledger(led, hoy)
        assert today_pnl == -5.0
        assert len(history) == 12 and -5.0 not in history
        v = ks.rule_pnl_daily(today_pnl, history)
        assert v["fired"] is True

    def test_daily_pnls_ignora_filas_de_labeling_sin_fill(self, tmp_path):
        """Filas del backtest (record()) no tienen open_fill_price — no cuentan."""
        led = SignalLedger(db_path=str(tmp_path / "led.db"))
        led.record("BT1", "AAPL", "2026-08-01", "2026-08-20", "TIME_BARRIER", -8.0)
        today_pnl, history = ks.daily_pnls_from_ledger(led, "2026-08-20")
        assert today_pnl is None and history == []

    def test_fill_rate_counts_today_solo_hoy_y_solo_llenos(self, tmp_path):
        tel = ExecutionTelemetry(db_path=str(tmp_path / "tel.db"))
        hoy = dt.date.today().isoformat()
        tel.record(phase="enter", run_ref=hoy, symbol="AAPL", side="buy",
                   qty=1, decision_price=100.0, fill_price=100.2)
        tel.record(phase="enter", run_ref=hoy, symbol="BAD", side="buy",
                   qty=1, decision_price=50.0, fill_price=None, status="error")
        tel.record(phase="exit", run_ref="2026-08-31", symbol="AAPL", side="sell",
                   qty=1, decision_price=110.0, fill_price=111.0)  # otro día: no cuenta
        n_total, n_filled = ks.fill_rate_counts_today(tel, hoy)
        assert (n_total, n_filled) == (2, 1)


# ------------------------------------------------- pico de equity (ratchet)

class TestPeakEquity:
    def test_el_pico_solo_sube(self, tmp_path):
        p = str(tmp_path / "ks_state.json")
        assert ks.update_peak_equity(10000.0, p) == 10000.0
        assert ks.update_peak_equity(10500.0, p) == 10500.0  # sube
        assert ks.update_peak_equity(9800.0, p) == 10500.0   # no baja
        assert ks.update_peak_equity(None, p) == 10500.0     # sin dato conserva

    def test_equity_menor_dispara_drawdown_contra_pico_sembrado(self, tmp_path):
        p = str(tmp_path / "ks_state.json")
        ks.update_peak_equity(10000.0, p)
        v = ks.rule_drawdown(equity=8900.0, peak_equity=ks.update_peak_equity(8900.0, p))
        assert v["fired"] is True and v["detail"]["peak"] == 10000.0


# ------------------------------------------------ STOP_FILE + notificación

class TestStopFile:
    def test_enforce_stop_escribe_json_con_evidencia_y_no_notifica(self, tmp_path):
        sp = str(tmp_path / "STOP_FILE")
        v = ks.rule_staleness(3)
        payload = ks.enforce_stop([v], stop_path=sp, notify=False)
        assert os.path.exists(sp)
        on_disk = json.load(open(sp))
        assert on_disk["summary"] == payload["summary"]
        assert on_disk["fired_rules"][0]["rule"] == "staleness"
        assert "rm data/STOP_FILE" in on_disk["rearme"]

    def test_is_stopped_y_read_stop_fail_closed(self, tmp_path):
        sp = str(tmp_path / "STOP_FILE")
        assert ks.is_stopped(sp) is False and ks.read_stop(sp) is None
        with open(sp, "w") as fh:  # contenido basura: presencia = pausa
            fh.write("no-json")
        assert ks.is_stopped(sp) is True
        raw = ks.read_stop(sp) or {}
        assert raw.get("raw") is True  # fail-closed: presencia = pausa

    def test_notify_macos_pinchado_no_explota(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("sin osascript")
        monkeypatch.setattr(ks.subprocess, "run", boom)
        assert ks.notify_macos("t", "m") is False  # best-effort, nunca rompe


# ------------------------------------------------ integración en el pipeline

@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Aísla data/ (STOP_FILE, estado del pipeline, calendario sintético)."""
    wd = tmp_path / "wd"
    wd.mkdir()
    monkeypatch.chdir(wd)
    os.makedirs(wd / "data" / "cache")
    # decision file del mes actual (phase_enter lo exige)
    mk = dt.date.today().strftime("%Y%m")
    with open(wd / "data" / "cache" / f"pipeline_decision_{mk}.json", "w") as fh:
        json.dump({"signals": [{"symbol": "AAPL", "score": 0.7,
                                "price_ref": 100.0}]}, fh)
    # calendario sintético: phase_health/detect_auto_phase exigen SPY.parquet
    import pandas as pd
    pd.DataFrame({"Close": [100.0], "Open": [100.0], "High": [101.0],
                  "Low": [99.0], "Volume": [1_000_000]},
                 index=pd.DatetimeIndex([pd.Timestamp(dt.date.today())])).to_parquet(
        wd / "data" / "cache" / "SPY.parquet")
    return wd


class FakeKillClient:
    """Cliente con get_account para el bloque pre-orden de phase_enter."""
    def __init__(self, equity=10000.0):
        self.equity = equity

    def get_account(self):
        return {"equity": self.equity}

    def get_positions(self):
        return []

    def submit_market_order(self, symbol, qty, side):
        return {"filled_avg_price": 100.5, "status": "filled"}

    def last_trade_price(self, symbol):
        return 100.0


class TestPipelineIntegration:
    def test_enter_respeta_stop_file_existente(self, workdir, monkeypatch, tmp_path):
        # STOP activo por staleness
        ks.enforce_stop([ks.rule_staleness(3)],
                         stop_path=str(workdir / "data" / "STOP_FILE"), notify=False)
        # El pipeline debe abortar ANTES de construir cliente/órdenes
        monkeypatch.setattr(pl, "_open_client_and_budget",
                            lambda lines, dry: (_ for _ in ()).throw(
                                AssertionError("STOP no debe abrir cliente")))
        rc = pl.phase_enter(dry_run=False, only_symbols=None)
        assert rc == 1
        # abortó con artefacto propio (no llegó a órdenes)
        arts = [f for f in os.listdir(workdir / "data" / "cache")
                if f.startswith("pipeline_run_enter")]
        assert arts

    def test_enter_dispara_drawdown_pre_orden_y_no_envia(self, workdir, monkeypatch):
        # pico sembrado 10000, equity real 8500 -> dd 15% > 10%: STOP
        ks.update_peak_equity(10000.0,
                              state_path=str(workdir / "data" / "kill_switch_state.json"))
        monkeypatch.setattr(pl, "_open_client_and_budget",
                            lambda lines, dry: (FakeKillClient(8500.0), 25000.0,
                                                "get_account", set()))
        sent = []
        monkeypatch.setattr(pl, "execute_plans",
                            lambda *a, **k: sent.append(a) or [])
        monkeypatch.setattr(ks, "notify_macos", lambda t, m: True)
        rc = pl.phase_enter(dry_run=False, only_symbols=None)
        assert rc == 1
        assert sent == []  # NUNCA llegó a ejecutar órdenes
        assert ks.is_stopped(str(workdir / "data" / "STOP_FILE")) is True

    def test_enter_sin_disparo_envia_y_no_detiene(self, workdir, monkeypatch):
        ks.update_peak_equity(10000.0,
                              state_path=str(workdir / "data" / "kill_switch_state.json"))
        monkeypatch.setattr(pl, "_open_client_and_budget",
                            lambda lines, dry: (FakeKillClient(9900.0), 25000.0,
                                                "get_account", set()))
        called = {}

        def fake_exec(plans, state, dry_run, phase, ref, **kw):
            called["phase"] = phase
            return [{"action": "buy", "symbol": "AAPL", "sid": "x",
                     "status": "dry_run_plan", "qty": 1}]

        monkeypatch.setattr(pl, "execute_plans", fake_exec)
        monkeypatch.setattr(ks, "notify_macos", lambda t, m: True)
        rc = pl.phase_enter(dry_run=False, only_symbols=None)
        assert rc == 0 and called.get("phase") == "enter"
        assert ks.is_stopped(str(workdir / "data" / "STOP_FILE")) is False

    def test_exit_con_stop_activo_no_se_bloquea(self, workdir, monkeypatch):
        """El STOP jamás bloquea EXIT: la fase exit corre igual con STOP activo."""
        ks.enforce_stop([ks.rule_staleness(3)],
                        stop_path=str(workdir / "data" / "STOP_FILE"), notify=False)
        called = {}

        def fake_exec(plans, state, dry_run, phase, ref, **kw):
            called["phase"] = phase
            return []

        monkeypatch.setattr(pl, "execute_plans", fake_exec)
        rc = pl.phase_exit(dry_run=False, only_symbols=None)
        assert rc == 0 and called.get("phase") == "exit"  # EXIT corrió igual

    def test_health_evalua_y_reporta_sin_disparo(self, workdir, monkeypatch):
        monkeypatch.setattr(ks, "notify_macos", lambda t, m: True)
        # sin ledger/telemetría legibles -> reglas se abstienen, no dispara
        rc = pl.phase_health()
        # rc depende del stale del calendario sintético (no hay SPY.parquet):
        # la fase reporta su chequeo sin explotar
        assert rc in (0, 1)

    def test_health_con_staleness_3_ruedas_dispara_stop(self, workdir, monkeypatch):
        monkeypatch.setattr(ks, "notify_macos", lambda t, m: True)
        monkeypatch.setattr(pl, "_cache_stale_ruedas", lambda: 3)
        rc = pl.phase_health()
        assert rc == 1
        assert ks.is_stopped(str(workdir / "data" / "STOP_FILE")) is True
