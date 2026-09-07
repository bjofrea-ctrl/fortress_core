"""Tests del contador de días limpios (A2 — PLAN_REMEDIO_BRECHAS_20260903 §A2).

Herméticos: sin red, sin Alpaca, sin DB. Fuentes sintéticas con el FORMATO
EXACTO de los logs reales (pipeline_diario.log, data_updater.log —
verificados contra producción 2026-09-05, incluida la corrida real con
``PRECIOS: ERROR - 84/102`` del 05-09 que dio el caso roto de (b)).
"""
import datetime as dt
import json

import pytest

from scripts import clean_days_counter as cc


# ---------------------------------------------------------------- helpers

def _run_block(date, hhmmss, hour_et, rc, phase="health"):
    """Bloque exacto de pipeline_diario.log para una corrida de la shell."""
    return [
        "=====================================================================",
        f"pipeline_daily_signal {date} {hhmmss} start (hour_ET={hour_et:02d})",
        f"Fase detectada: {phase}",
        "Pipeline HEALTH",
        "========================================",
        "Cache: ultimo habil hace 1 dias -> OK",
        "Out: data/cache/pipeline_run_health_x.txt",
        f"pipeline_daily_signal end rc={rc}",
    ]


def _corrida_block(date, ok=True, n_ok=102, n_fail=0, hora="22:00:00"):
    """Bloque de data_updater.log para una corrida (formato real inicio/fin).

    El encabezado ``Corrida <ts>`` va DESPUÉS del paso de precios y NO
    delimita el bloque — el delimitador real es ``[ts] data_updater:
    inicio`` … ``data_updater: fin`` (verificado contra el log real, donde
    una corrida manual del mediodía con PRECIOS: ERROR quedaba fuera del
    parseo por ``Corrida`` — bug fixeado contra el caso del 02-09).
    """
    lines = [
        f"[{date} {hora}] data_updater: inicio",
    ]
    if ok:
        lines.append(f"precios: {n_ok}/{n_ok} OK")
    else:
        n_fail = n_fail or n_ok  # default plausible: todo el universo cayó
        lines.append(f"  PYPL   ERROR: HTTPSConnectionPool(Read timeout)")
        lines.append(f"PRECIOS: ERROR - {n_fail}/{n_ok} símbolos fallaron (ver líneas ERROR arriba)")
        lines.append(f"[{date} 22:03:52] PRECIOS: ERROR - paso precios rc=1")
    lines += [
        "=" * 60,
        f"Corrida {date}T22:03:00",
        "Universo: 102 símbolos (100 con earnings, 2 ETF excluidos: SPY, QQQ)",
        "[AAPL] OK — 0 8-K(s) nuevo(s), 8 listados",
        f"[{date} 22:05:00] data_updater: fin (acumulacion rc=0)",
    ]
    return lines


def _reconcile_line(date, hhmmss, orphan=0, unexplained=0):
    return (f"{date}T{hhmmss} [pipeline] reconcile "
            f"orphan_closed={orphan} unexplained={unexplained}")


def _sources(days_spec):
    """Construye (pipeline_text, updater_text, state) desde una especificación.

    days_spec: {fecha: {"runs": {hour: rc}, "precios_ok": bool,
                        "reconcile": (orphan, unexplained) | None}}
    """
    plines, ulines = [], []
    for date in sorted(days_spec):
        spec = days_spec[date]
        for hour, rc in sorted(spec.get("runs", {}).items()):
            hh = {9: "09:35:02", 15: "15:40:04", 22: "22:10:02"}[hour]
            plines += _run_block(date, hh, hour, rc)
        if spec.get("runs") or spec.get("precios_ok") is not None:
            ulines += _corrida_block(date, ok=spec.get("precios_ok", True),
                                     n_fail=spec.get("n_fail", 0))
        rec = spec.get("reconcile")
        if rec:
            plines.append(_reconcile_line(date, "22:12:00",
                                         orphan=rec[0], unexplained=rec[1]))
    return "\n".join(plines), "\n".join(ulines)


def _report(days_spec, state=None, reconciler_start=None):
    ptext, utext = _sources(days_spec)
    kwargs = {"pipeline_log_text": ptext, "updater_log_text": utext,
              "state_reconcile": state}
    if reconciler_start is not None:
        kwargs["reconciler_start"] = reconciler_start
    return cc.build_report_from_text(**kwargs)


# --------------------------------------------- parseo de formatos reales

def test_parse_pipeline_runs_formato_real():
    text = "\n".join(_run_block("2026-09-04", "09:35:00", 9, 0)
                     + _run_block("2026-09-04", "22:10:04", 22, 2))
    runs = cc.parse_pipeline_runs(text)
    assert runs == {"2026-09-04": {9: 0, 22: 2}}


def test_parse_pipeline_runs_ignora_corrida_fuera_de_ventana():
    # kickstart manual a las 11:33 (hour_ET=11) — no cuenta para (a)
    text = "\n".join(_run_block("2026-08-27", "11:33:57", 11, 0))
    assert cc.parse_pipeline_runs(text) == {}


def test_parse_updater_days_detecta_error_de_precios():
    text = "\n".join(_corrida_block("2026-09-05", ok=False, n_fail=84))
    days = cc.parse_updater_days(text)
    assert "2026-09-05" in days
    assert any("PRECIOS: ERROR" in ln for ln in days["2026-09-05"])


def test_parse_reconcile_lines_ultima_del_dia_manda():
    text = "\n".join([
        _reconcile_line("2026-09-04", "22:12:00", orphan=1, unexplained=0),
        _reconcile_line("2026-09-04", "23:30:00", orphan=0, unexplained=2),
    ])
    by_day = cc.parse_reconcile_lines(text)
    assert by_day["2026-09-04"][-1]["unexplained"] == 2


# ---------------------------------------------- condición (a)

def test_condicion_a_exige_las_3_ventanas_rc0():
    assert cc.evaluar_condicion_a({"2026-09-04": {9: 0, 15: 0, 22: 0}},
                                  "2026-09-04")["ok"] is True
    # falta la de las 15:40
    r = cc.evaluar_condicion_a({"2026-09-04": {9: 0, 22: 0}}, "2026-09-04")
    assert r["ok"] is False and "sin corrida" in r["reason"]
    # una ventana con rc=2 (hash drift del 05-09 real)
    r = cc.evaluar_condicion_a({"2026-09-05": {9: 2, 15: 2, 22: 2}}, "2026-09-05")
    assert r["ok"] is False and "rc!=0" in r["reason"]


# ---------------------------------------------- condición (b)

def test_condicion_b_sin_corrida_no_habil():
    r = cc.evaluar_condicion_b({}, "2026-09-06")  # domingo sin updater
    assert r["ok"] is False and not r["corrida"]


def test_condicion_b_error_de_precios_rompe():
    text = "\n".join(_corrida_block("2026-09-05", ok=False, n_fail=84))
    days = cc.parse_updater_days(text)
    r = cc.evaluar_condicion_b(days, "2026-09-05")
    assert r["ok"] is False and "84/102" in r["reason"]


def test_condicion_b_error_de_mediodia_en_segunda_corrida_rompe():
    """Caso REAL del 02-09: corrida manual del mediodía con PRECIOS: ERROR
    + corrida nocturna OK. El bug previo (parseo por 'Corrida <ts>') perdía
    la del mediodía y reportaba b=OK en un día que falló."""
    text = "\n".join(
        _corrida_block("2026-09-02", ok=False, n_fail=1, hora="12:10:06")
        + _corrida_block("2026-09-02", ok=True)
    )
    days = cc.parse_updater_days(text)
    assert "2026-09-02" in days
    r = cc.evaluar_condicion_b(days, "2026-09-02")
    assert r["ok"] is False and "1/102" in r["reason"]


def test_condicion_b_ok_con_corrida_unica_nocturna():
    text = "\n".join(_corrida_block("2026-09-03", ok=True))
    days = cc.parse_updater_days(text)
    r = cc.evaluar_condicion_b(days, "2026-09-03")
    assert r["ok"] is True and r["corrida"] is True
    assert r["precios_ok_line"].startswith("precios: 102/102")


# ---------------------------------------------- condición (c)

def test_condicion_c_unexplained0_ok_orphan_cerrar_es_su_trabajo():
    text = _reconcile_line("2026-09-04", "22:12:00", orphan=3, unexplained=0)
    by_day = cc.parse_reconcile_lines(text)
    r = cc.evaluar_condicion_c(by_day, None, "2026-09-04",
                               reconciler_start=dt.date(2026, 9, 4))
    assert r["ok"] is True and r["orphan_closed"] == 3


def test_condicion_c_unexplained_positivo_rompe():
    text = _reconcile_line("2026-09-04", "22:12:00", orphan=0, unexplained=1)
    by_day = cc.parse_reconcile_lines(text)
    r = cc.evaluar_condicion_c(by_day, None, "2026-09-04",
                               reconciler_start=dt.date(2026, 9, 4))
    assert r["ok"] is False and r["unexplained"] == 1


def test_condicion_c_state_json_como_fuente_cuando_no_hay_linea():
    state = {"exit_date": "2026-09-04", "orphan_closed": 0, "unexplained": 0}
    r = cc.evaluar_condicion_c({}, state, "2026-09-04",
                               reconciler_start=dt.date(2026, 9, 4))
    assert r["ok"] is True and r["source"] == "pipeline_state.json"
    # state de OTRO día no sirve como evidencia de este
    r2 = cc.evaluar_condicion_c({}, state, "2026-09-05",
                                reconciler_start=dt.date(2026, 9, 4))
    assert r2["ok"] is False


def test_condicion_c_dia_previo_al_arranque_es_unverified():
    r = cc.evaluar_condicion_c({}, None, "2026-09-02",
                               reconciler_start=dt.date(2026, 9, 4))
    assert r.get("status") == "UNVERIFIED_C" and r["ok"] is False


def test_condicion_c_sin_reconciler_hoy_es_unverified_no_roto():
    # día hábil posterior al arranque sin corrida del reconciler (solo corre
    # en decide): UNVERIFIED_C — evidencia ausente, no fallo
    r = cc.evaluar_condicion_c({}, None, "2026-09-05",
                               reconciler_start=dt.date(2026, 9, 4))
    assert r.get("status") == "UNVERIFIED_C"


# ---------------------------------------------- racha (ticket A2, literal)

def test_racha_avanza_con_3_dias_limpios_completos():
    """Ticket A2: 3 días sintéticos completos → el contador AVANZA."""
    days = {
        "2026-09-02": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
        "2026-09-03": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (1, 0)},  # cerrar huérfana NO rompe
        "2026-09-04": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
    }
    rep = _report(days, reconciler_start=dt.date(2026, 9, 1))
    assert rep["streak"] == 3
    assert rep["total_clean"] == 3
    assert all(d["clean"] for d in rep["days"])


def test_dia_con_condicion_rota_no_avanza_el_contador():
    """Ticket A2: un día con una condición rota → NO avanza (y corta racha)."""
    days = {
        "2026-09-02": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
        # 05-09 real: las 3 corridas rc=2 (hash drift) + PRECIOS ERROR 84/102
        "2026-09-03": {"runs": {9: 2, 15: 2, 22: 2}, "precios_ok": False,
                       "n_fail": 84, "reconcile": None},
    }
    rep = _report(days, reconciler_start=dt.date(2026, 9, 1))
    assert rep["days"][0]["clean"] is True
    assert rep["days"][1]["clean"] is False
    assert rep["streak"] == 0  # el día roto cortó la racha
    # el JSON muestra el PORQUÉ (evidencia por condición)
    conds = rep["days"][1]["conditions"]
    assert "rc!=0" in conds["a"]["reason"]
    assert "84/102" in conds["b"]["reason"]
    assert conds["c"].get("status") == "UNVERIFIED_C"


def test_cada_condicion_rota_sola_basta_para_no_contar():
    base = {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True, "reconcile": (0, 0)}
    # (a) rota sola
    rep = _report({"2026-09-02": {**base, "runs": {9: 1, 15: 0, 22: 0}}},
                  reconciler_start=dt.date(2026, 9, 1))
    assert rep["days"][0]["clean"] is False
    # (b) rota sola
    rep = _report({"2026-09-02": {**base, "precios_ok": False}},
                  reconciler_start=dt.date(2026, 9, 1))
    assert rep["days"][0]["clean"] is False
    # (c) rota sola: unexplained=1
    rep = _report({"2026-09-02": {**base, "reconcile": (0, 1)}},
                  reconciler_start=dt.date(2026, 9, 1))
    assert rep["days"][0]["clean"] is False


def test_unverified_no_corta_racha_pero_no_suma():
    # 02-09 limpio, 03-09 sin reconciler (UNVERIFIED_C), 04-09 limpio:
    # la racha sigue contando los limpios — no se rompe retroactivamente
    days = {
        "2026-09-02": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
        "2026-09-03": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": None},
        "2026-09-04": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
    }
    rep = _report(days, reconciler_start=dt.date(2026, 9, 1))
    assert [d["clean"] for d in rep["days"]] == [True, False, True]
    assert rep["days"][1]["unverified_c"] is True
    assert rep["streak"] == 2  # 02-09 + 04-09; el unverified no cortó


def test_fin_de_semana_no_aparece_ni_corta():
    # sábado 05-09 sin updater (no hábil) → no está en la tabla; la racha
    # del viernes queda intacta. Evidencia solo el viernes 04-09 → el
    # contador evalúa los weekdays 02/03/04-09 (gate arranca 02-09), el
    # 02 y 03 sin updater fallan (b), el 04 suma.
    days = {
        "2026-09-04": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
    }
    rep = _report(days, reconciler_start=dt.date(2026, 9, 4))
    assert [d["date"] for d in rep["days"]] == ["2026-09-02", "2026-09-03", "2026-09-04"]
    assert rep["days"][-1]["clean"] is True
    assert rep["streak"] == 1


def test_weekday_sin_corrida_del_updater_rompe_racha():
    """Semántica de racha ininterrumpida (C1): un weekday con el updater
    muerto es un día con el tubo ROTO, no un día invisible. Con la corrida
    del jueves 03-09 como última evidencia, el contador evalúa hasta ahí;
    si agregamos evidencia el viernes 04-09 PERO el jueves-no-corrió ya no
    puede pasar — este test fija la semántica con un weekday intermedio
    sin updater entre dos días con evidencia."""
    days = {
        "2026-09-02": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
        # 03-09: weekday SIN updater (tubo muerto) — no está en el spec
        "2026-09-04": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
    }
    rep = _report(days, reconciler_start=dt.date(2026, 9, 1))
    fechas = [d["date"] for d in rep["days"]]
    assert fechas == ["2026-09-02", "2026-09-03", "2026-09-04"]  # 03-09 evaluado
    d03 = rep["days"][1]
    assert d03["clean"] is False and not d03["unverified_c"]
    assert "sin corrida del updater" in d03["conditions"]["b"]["reason"]
    assert rep["streak"] == 1  # solo el 04-09; el 03-09 la cortó


def test_missing_after_daily_es_fallo_verificado_corta_racha():
    """Reconciler diario activo (dos weekdays adyacentes con líneas) y un
    weekday posterior sin línea propia → MISSING_AFTER_DAILY: la corrida
    22:10 no dejó evidencia = fallo, no ausencia. Corta la racha."""
    days = {
        "2026-09-07": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
        "2026-09-08": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},   # cadencia diaria activa
        # 09-09: reconciler diario activo PERO sin línea del día (corrida
        # 22:10 rota) — MISSING_AFTER_DAILY, no UNVERIFIED_C
        "2026-09-09": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": None},
        "2026-09-10": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                       "reconcile": (0, 0)},
    }
    rep = _report(days, reconciler_start=dt.date(2026, 9, 1))
    d09 = next(d for d in rep["days"] if d["date"] == "2026-09-09")
    assert d09["conditions"]["c"].get("status") == "MISSING_AFTER_DAILY"
    assert d09["clean"] is False and not d09["unverified_c"]
    assert rep["streak"] == 1  # solo el 10-09; el 09-09 cortó


def test_lineas_de_test_no_activan_cadencia_diaria():
    """Anti-contaminación: las líneas reconcile FALSAS que versiones previas
    del test de A1 dejaban caer a horas arbitrarias (16:23, 19:37, 23:57…)
    NO deben activar la cadencia diaria — solo dos líneas en weekdays
    adyacentes (patrón de la corrida real 22:10) la activan."""
    # Todas las líneas caen el MISMO día (05-09, sábado) a horas raras:
    # patrón de corridas de pytest, no de la shell 22:10.
    text = "\n".join([
        _reconcile_line("2026-09-05", "16:23:24", orphan=1, unexplained=0),
        _reconcile_line("2026-09-05", "19:37:22", orphan=1, unexplained=0),
        _reconcile_line("2026-09-05", "23:57:15", orphan=1, unexplained=0),
        _reconcile_line("2026-09-06", "01:00:14", orphan=1, unexplained=0),
    ])
    by_day = cc.parse_reconcile_lines(text)
    assert cc.daily_reconcile_active(by_day, "2026-09-05") is False
    assert cc.daily_reconcile_active(by_day, "2026-09-06") is False
    # Dos weekdays adyacentes (lun+mar) SÍ activan
    text2 = "\n".join([
        _reconcile_line("2026-09-07", "22:12:00", orphan=0, unexplained=0),
        _reconcile_line("2026-09-08", "22:12:00", orphan=0, unexplained=0),
    ])
    by_day2 = cc.parse_reconcile_lines(text2)
    assert cc.daily_reconcile_active(by_day2, "2026-09-07") is True
    assert cc.daily_reconcile_active(by_day2, "2026-09-08") is True
    # y los días siguientes a la cadena también quedan activos
    assert cc.daily_reconcile_active(by_day2, "2026-09-10") is True


# ---------------------------------------------- salida y CLI

def test_save_report_escribe_json_atomico(tmp_path):
    days = {"2026-09-04": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                           "reconcile": (0, 0)}}
    rep = _report(days, reconciler_start=dt.date(2026, 9, 4))
    out = str(tmp_path / "clean_days.json")
    cc.save_report(rep, out)
    with open(out, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["streak"] == 1
    assert on_disk["definicion"].startswith("día limpio")
    # evidencia por día presente en el JSON final
    d04 = next(d for d in on_disk["days"] if d["date"] == "2026-09-04")
    assert set(d04["conditions"]) == {"a", "b", "c"}
    assert d04["conditions"]["b"]["precios_ok_line"].startswith("precios:")


def test_main_stdout_no_toca_disco(tmp_path, capsys, monkeypatch):
    days = {"2026-09-04": {"runs": {9: 0, 15: 0, 22: 0}, "precios_ok": True,
                           "reconcile": (0, 0)}}
    ptext, utext = _sources(days)
    monkeypatch.setattr(cc, "build_report",
                        lambda: cc.build_report_from_text(
                            pipeline_log_text=ptext, updater_log_text=utext,
                            state_reconcile=None))
    rc = cc.main(["--stdout"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["streak"] == 1
    assert not (tmp_path / "clean_days.json").exists()
