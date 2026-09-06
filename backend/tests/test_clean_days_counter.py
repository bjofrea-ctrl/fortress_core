"""
Tests del contador de días limpios (A2) — PLAN_REMEDIO_BRECHAS_20260903.md §A2.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from app.core import clean_days
from app.core.clean_days import (
    CLEAN_DAYS_PATH,
    GATE_START_DATE,
    _trading_days_calendar,
    compute_streak,
    evaluate_day,
    evaluate_window,
    make_record,
    run,
    write_record,
)
from app.core.gate_window import GATE_START_DATE as GWD

# ------------------------------ helpers ---------------------------------


def _pipeline_rc_line(d_iso: str, rc: int) -> str:
    """Output típico de la fase pipeline_daily_signal (línea 'rc=N').
    NO incluye líneas del reconciler (esos los inyectan tests puntuales)."""
    return (
        f"{d_iso}T22:10:01 [pipeline_daily_signal] start\n"
        f"{d_iso}T22:11:05 pipeline_daily_signal end rc={rc}\n"
    )


def _updater_clean(d_iso: str) -> str:
    return (
        f"[{d_iso} 22:00:01] data_updater: inicio\n"
        f"  SPY    hasta 2026-09-04\n"
        f"  AAPL   hasta 2026-09-04\n"
        f"precios: 50/50 OK\n"
        f"[{d_iso} 22:05:30] data_updater: fin (acumulacion rc=0)\n"
    )


def _updater_con_error(d_iso: str) -> str:
    return (
        f"[{d_iso} 22:00:01] data_updater: inicio\n"
        f"  AAPL   PRECIOS: ERROR: yfinance timeout\n"
        f"precios: 49/50 OK\n"
        f"[{d_iso} 22:05:30] data_updater: fin (acumulacion rc=1)\n"
    )


def _state_with_reconcile(d_iso: str, unexplained: int) -> dict:
    return {
        "entries": {},
        "months": {},
        "reconcile": {
            "orphan_closed": 0,
            "unexplained": unexplained,
            "timestamp": f"{d_iso}T22:10:33",
        },
    }


# ------------------------------ tests puros -----------------------------


def test_evaluate_day_clean_returns_true():
    d = _dt.date(2026, 9, 3)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=0)
    updater = _updater_clean(d.isoformat())
    state = _state_with_reconcile(d.isoformat(), 0)
    ev = evaluate_day(d, pipeline, updater, state)
    assert ev["clean"] is True, ev
    assert ev["reasons"] == []
    assert ev["evidence"]["a_pipeline_rc0"]["rc_ok"] is True
    assert ev["evidence"]["b_updater_no_precios_error"]["present"] is True
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["verdict"] == "OK"


def test_evaluate_day_pipeline_rc_nonzero_marks_not_clean():
    d = _dt.date(2026, 9, 3)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=2)
    updater = _updater_clean(d.isoformat())
    state = _state_with_reconcile(d.isoformat(), 0)
    ev = evaluate_day(d, pipeline, updater, state)
    assert ev["clean"] is False
    assert any("rc!=0" in r for r in ev["reasons"])


def test_evaluate_day_no_pipeline_run_marks_not_clean():
    d = _dt.date(2026, 9, 3)
    pipeline = ""
    updater = _updater_clean(d.isoformat())
    state = _state_with_reconcile(d.isoformat(), 0)
    ev = evaluate_day(d, pipeline, updater, state)
    assert ev["clean"] is False
    assert any("no corrió" in r for r in ev["reasons"])


def test_evaluate_day_precios_error_marks_not_clean():
    d = _dt.date(2026, 9, 3)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=0)
    updater = _updater_con_error(d.isoformat())
    state = _state_with_reconcile(d.isoformat(), 0)
    ev = evaluate_day(d, pipeline, updater, state)
    assert ev["clean"] is False
    assert any("PRECIOS: ERROR" in r for r in ev["reasons"])


def test_evaluate_day_unexplained_gt0_marks_not_clean():
    d = _dt.date(2026, 9, 3)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=0)
    updater = _updater_clean(d.isoformat())
    state = _state_with_reconcile(d.isoformat(), 2)
    ev = evaluate_day(d, pipeline, updater, state)
    assert ev["clean"] is False
    assert any("unexplained=2" in r for r in ev["reasons"])
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["verdict"] == "FAIL(2)"


def test_evaluate_day_no_reconcile_at_all_is_unverified_c():
    """UNVERIFIED_C solo cuando NO hay reconcile en state NI en log del día
    ni de días previos (estado anterior al primer run del reconciler A1)."""
    d = _dt.date(2026, 9, 2)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=0)
    updater = _updater_clean(d.isoformat())
    ev = evaluate_day(d, pipeline, updater, None)
    assert ev["clean"] is False
    assert any("UNVERIFIED_C" in r for r in ev["reasons"])
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["verdict"] == "UNVERIFIED_C"


def test_evaluate_day_unverified_c_when_state_empty_and_log_silent():
    """state sin reconcile y log sin líneas de reconcile -> UNVERIFIED_C."""
    d = _dt.date(2026, 9, 2)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=0)
    updater = _updater_clean(d.isoformat())
    ev = evaluate_day(d, pipeline, updater, {"entries": {}})
    assert ev["clean"] is False
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["verdict"] == "UNVERIFIED_C"


def test_evaluate_day_uses_previous_reconcile_from_state_if_today_missing():
    """Si el reconciler no corrió HOY pero sí en un run previo, usa ese valor
    (el reconciler A1 solo corre mensual, fin de mes 22:10)."""
    d = _dt.date(2026, 9, 15)
    pipeline = _pipeline_rc_line(d.isoformat(), rc=0)
    updater = _updater_clean(d.isoformat())
    state = {
        "entries": {},
        "months": {},
        "reconcile": {
            "orphan_closed": 0,
            "unexplained": 0,
            "timestamp": "2026-09-01T22:10:33",
        },
    }
    ev = evaluate_day(d, pipeline, updater, state)
    assert ev["clean"] is True, ev
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["source"] == "state"
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["verdict"] == "OK"


def test_evaluate_day_falls_back_to_log_when_state_empty():
    """Si state no tiene 'reconcile' pero el log tiene líneas DEL DÍA,
    usa la del día (source='log')."""
    d = _dt.date(2026, 9, 15)
    pipeline = (
        _pipeline_rc_line(d.isoformat(), rc=0)
        + f"{d.isoformat()}T22:10:33 [pipeline] reconcile orphan_closed=0 unexplained=0\n"
    )
    updater = _updater_clean(d.isoformat())
    ev = evaluate_day(d, pipeline, updater, {"entries": {}})
    assert ev["clean"] is True
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["source"] == "log"


def test_evaluate_day_uses_previous_log_reconcile_when_state_empty():
    """Si state sin reconcile y log con reconcile de día ANTERIOR, usa el
    del log (source='log_prev')."""
    d = _dt.date(2026, 9, 15)
    pipeline = (
        _pipeline_rc_line(d.isoformat(), rc=0)
        + "2026-09-01T22:10:33 [pipeline] reconcile orphan_closed=0 unexplained=0\n"
    )
    updater = _updater_clean(d.isoformat())
    ev = evaluate_day(d, pipeline, updater, {"entries": {}})
    assert ev["clean"] is True
    assert ev["evidence"]["c_reconcile_unexplained_zero"]["source"] == "log_prev"


def test_trading_days_excludes_weekends():
    days = _trading_days_calendar(_dt.date(2026, 9, 4), _dt.date(2026, 9, 7))
    assert [d.isoformat() for d in days] == ["2026-09-04", "2026-09-07"]


def test_compute_streak_counts_consecutive_from_end():
    """El contrato: racha = limpios consecutivos al final hasta el primer roto.

    [L, F, L, L, L, L] -> los últimos 4 son consecutivos al final sin roto
    entre ellos (el F está antes). racha = 4.
    """
    days = [
        {"date": "2026-09-02", "clean": True},
        {"date": "2026-09-03", "clean": False},
        {"date": "2026-09-04", "clean": True},
        {"date": "2026-09-05", "clean": True},
        {"date": "2026-09-08", "clean": True},
        {"date": "2026-09-09", "clean": True},
    ]
    streak, start = compute_streak(days)
    assert streak == 4
    assert start == "2026-09-04"


def test_compute_streak_breaks_on_intermediate_fails():
    """Si hay un F entre dos L al final, la racha es solo los del final."""
    days = [
        {"date": "2026-09-02", "clean": True},
        {"date": "2026-09-03", "clean": True},
        {"date": "2026-09-04", "clean": False},  # rompe
        {"date": "2026-09-05", "clean": True},
        {"date": "2026-09-08", "clean": True},
    ]
    streak, start = compute_streak(days)
    assert streak == 2
    assert start == "2026-09-05"


def test_compute_streak_zero_when_last_day_not_clean():
    days = [
        {"date": "2026-09-08", "clean": True},
        {"date": "2026-09-09", "clean": False},
    ]
    streak, start = compute_streak(days)
    assert streak == 0
    assert start is None


def test_compute_streak_full_clean():
    days = [
        {"date": "2026-09-02", "clean": True},
        {"date": "2026-09-03", "clean": True},
    ]
    streak, start = compute_streak(days)
    assert streak == 2
    assert start == "2026-09-02"


def test_compute_streak_empty_list():
    assert compute_streak([]) == (0, None)


def test_make_record_includes_streak_and_definition():
    days = [
        {"date": "2026-09-02", "clean": True, "reasons": [], "evidence": {}},
        {"date": "2026-09-03", "clean": True, "reasons": [], "evidence": {}},
    ]
    rec = make_record(days, generated_at="2026-09-03T22:11:00")
    assert rec["schema_version"] == 1
    assert rec["gate_start"] == GATE_START_DATE.isoformat()
    assert rec["streak"] == 2
    assert rec["streak_started"] == "2026-09-02"
    assert rec["n_clean"] == 2
    assert rec["n_total"] == 2
    assert rec["last_evaluated"] == "2026-09-03"
    assert "a_pipeline_rc0" in rec["definition"]


def test_evaluate_window_order_preserved():
    days = [_dt.date(2026, 9, 2), _dt.date(2026, 9, 3), _dt.date(2026, 9, 4)]
    pipeline = "".join(_pipeline_rc_line(d.isoformat(), rc=0) for d in days)
    updater = "".join(_updater_clean(d.isoformat()) for d in days)
    state = _state_with_reconcile("2026-09-02", 0)
    evals = evaluate_window(days, pipeline, updater, state)
    assert [e["date"] for e in evals] == ["2026-09-02", "2026-09-03", "2026-09-04"]


def test_write_record_is_atomic(tmp_path):
    out = tmp_path / "clean_days.json"
    rec = make_record([{"date": "2026-09-02", "clean": True, "reasons": [], "evidence": {}}])
    write_record(rec, str(out))
    assert out.exists()
    assert not (tmp_path / "clean_days.json.tmp").exists()
    loaded = json.loads(out.read_text())
    assert loaded["streak"] == 1


def test_run_end_to_end_with_custom_paths(tmp_path):
    """run() lee los paths default pero podemos cambiarlos — verifica que persiste
    y devuelve un record con la forma correcta."""
    pipeline_log = tmp_path / "pipeline.log"
    updater_log = tmp_path / "updater.log"
    state_path = tmp_path / "pipeline_state.json"
    out_path = tmp_path / "clean_days.json"
    pipeline_text = ""
    updater_text = ""
    for d in [_dt.date(2026, 9, 2), _dt.date(2026, 9, 3), _dt.date(2026, 9, 4)]:
        pipeline_text += _pipeline_rc_line(d.isoformat(), rc=0)
        updater_text += _updater_clean(d.isoformat())
    state = _state_with_reconcile("2026-09-02", 0)
    pipeline_log.write_text(pipeline_text)
    updater_log.write_text(updater_text)
    state_path.write_text(json.dumps(state))
    rec = run(
        today=_dt.date(2026, 9, 4),
        pipeline_log_path=str(pipeline_log),
        updater_log_path=str(updater_log),
        state_path=str(state_path),
        output_path=str(out_path),
    )
    assert out_path.exists()
    assert rec["last_evaluated"] == "2026-09-04"
    assert rec["n_total"] == 3
    assert rec["n_clean"] == 3
    assert rec["streak"] == 3


def test_run_handles_missing_logs_gracefully(tmp_path):
    """Si los logs no existen (worktree sin actividad), NO debe fallar —
    devuelve un record con todos los días FAIL pero persiste."""
    out_path = tmp_path / "clean_days.json"
    rec = run(
        today=_dt.date(2026, 9, 4),
        pipeline_log_path=str(tmp_path / "no_pipeline.log"),
        updater_log_path=str(tmp_path / "no_updater.log"),
        state_path=str(tmp_path / "no_state.json"),
        output_path=str(out_path),
    )
    assert out_path.exists()
    assert rec["n_clean"] == 0
    assert rec["streak"] == 0
    assert all(not d["clean"] for d in rec["days"])


def test_evidence_keys_match_definition():
    d = _dt.date(2026, 9, 3)
    ev = evaluate_day(d, "", "", None)
    assert set(ev["evidence"].keys()) == {
        "a_pipeline_rc0",
        "b_updater_no_precios_error",
        "c_reconcile_unexplained_zero",
    }


def test_constant_paths_are_repo_relative():
    assert CLEAN_DAYS_PATH == os.path.join("data", "clean_days.json")
    assert not os.path.isabs(CLEAN_DAYS_PATH)


def test_gate_start_anchor_from_gate_window_module():
    """A2 y A7 usan el MISMO GATE_START_DATE — si A7 cambia, A2 también."""
    assert clean_days.GATE_START_DATE == GWD
