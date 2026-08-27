"""Tests del reporte mensual (Frente 2, Semana 2).

Mecanismo puro contra fixtures — NO consume presupuesto de trials ni toca
trial_registry (ver docstring de app/core/monthly_report.py):
- agrupación variante×mes desde el signal_ledger (default cuando la fila
  no etiqueta factors_json["variant"]);
- Sharpe realizado nativo (mean/std ddof=1) con veredictos estructurales
  sin datos suficientes (SIN_DATOS / DEGENERADO);
- comparación contra expectativa (EN_CALIBRACION / DEBAJO_ESPERADO /
  NEGATIVO / ESPERADO_NO_DEFINIDO) con archivo de expectativas;
- bitácora acumulada en monthly_report_log, idempotente al regenerar.
"""
import json

from app.core.monthly_report import DEFAULT_VARIANT, MonthlyReporter, compute_month_stats, month_key
from app.core.signal_ledger import SignalLedger


def _seed(led: SignalLedger, sid, sym, entry, exit_d, pnl,
          factors=None, qty=10, price=100.0):
    led.open_order(signal_id=sid, symbol=sym, entry_date=entry, qty=qty,
                   open_fill_price=price, factors=factors)
    led.close_order(signal_id=sid, exit_date=exit_d, exit_reason="TP",
                    pnl_r=pnl, close_fill_price=price * (1 + pnl))


def _reporter(db_path, **kw):
    kw.setdefault("expectations_path", None)
    return MonthlyReporter(db_path=db_path, **kw)


# -- utilidades puras --------------------------------------------------------
def test_month_key():
    assert month_key("2026-08-25") == "2026-08"
    assert month_key("2026-08-25T10:00:00") == "2026-08"


def test_compute_month_stats_basico():
    s = compute_month_stats([0.1, 0.3])
    assert abs(s["mean"] - 0.2) < 1e-12
    # std muestral ddof=1 de [0.1,0.3] = 0.141421...
    assert abs(s["sharpe"] - 0.2 / 0.14142135623730951) < 1e-9
    assert s["base_verdict"] is None


def test_compute_month_stats_sin_datos_y_degenerado():
    assert compute_month_stats([0.05])["base_verdict"] == "SIN_DATOS"
    assert compute_month_stats([])["base_verdict"] == "SIN_DATOS"
    deg = compute_month_stats([0.02, 0.02])
    assert deg["base_verdict"] == "DEGENERADO" and deg["sharpe"] is None


# -- agrupación y veredictos --------------------------------------------------
def test_agrupa_por_variante_y_mes_con_default(tmp_path):
    db = str(tmp_path / "rep.db")
    led = SignalLedger(db)
    _seed(led, "a1", "AAA", "2026-07-01", "2026-07-10", 0.10)          # default
    _seed(led, "a2", "BBB", "2026-07-05", "2026-07-20", 0.20)          # default
    _seed(led, "b1", "CCC", "2026-08-01", "2026-08-15", 0.05,
          factors={"variant": "a5_quality_value"})                     # explícita
    led.open_order(signal_id="abierta", symbol="DDD",
                   entry_date="2026-07-02", qty=5,
                   open_fill_price=50.0)                               # abierta: NO cuenta
    rep = _reporter(db)
    rows = {(r["variant"], r["month"]): r for r in rep.month_rows()}
    assert set(rows) == {(DEFAULT_VARIANT, "2026-07"),
                         ("a5_quality_value", "2026-08")}
    assert rows[(DEFAULT_VARIANT, "2026-07")]["n"] == 2


def test_verdict_en_calibracion(tmp_path):
    db = str(tmp_path / "v1.db")
    led = SignalLedger(db)
    _seed(led, "x1", "AAA", "2026-07-01", "2026-07-10", 0.10)
    _seed(led, "x2", "BBB", "2026-07-05", "2026-07-20", 0.30)
    # sharpe nativo = 0.2/0.14142 ≈ 1.414 >> 0.5 × 0.383816 esperado
    out = _reporter(db).generate(month="2026-07", persist=False)
    assert out["rows"][0]["verdict"] == "EN_CALIBRACION"


def test_verdict_debajo_esperado_y_negativo(tmp_path):
    db = str(tmp_path / "v2.db")
    led = SignalLedger(db)
    _seed(led, "d1", "AAA", "2026-07-01", "2026-07-10", -0.10)   # sharpe≈+0.034
    _seed(led, "d2", "BBB", "2026-07-05", "2026-07-20", 0.11)    # >0 pero << umbral
    _seed(led, "e1", "CCC", "2026-08-01", "2026-08-10", -0.10)
    _seed(led, "e2", "DDD", "2026-08-05", "2026-08-20", -0.02)   # negativo
    out = _reporter(db).generate()
    verd = {(r["month"]): r["verdict"] for r in out["rows"]}
    assert verd["2026-07"] == "DEBAJO_ESPERADO"
    assert verd["2026-08"] == "NEGATIVO"


def test_verdict_estructurales_y_esperado_no_definido(tmp_path):
    db = str(tmp_path / "v3.db")
    led = SignalLedger(db)
    _seed(led, "s1", "AAA", "2026-07-01", "2026-07-10", 0.05)            # 1 oficio
    _seed(led, "g1", "BBB", "2026-08-01", "2026-08-10", 0.02)
    _seed(led, "g2", "CCC", "2026-08-05", "2026-08-20", 0.02)            # degenerado
    # variante sin expectativa y con dispersion suficiente para llegar al
    # chequeo de expectativa (el estructural SIN_DATOS precede por diseño)
    _seed(led, "n1", "DDD", "2026-09-01", "2026-09-10", -0.20,
          factors={"variant": "variante_sin_expectativa"})
    _seed(led, "n2", "EEE", "2026-09-05", "2026-09-20", 0.60,
          factors={"variant": "variante_sin_expectativa"})
    out = _reporter(db).generate()
    verd = {r["month"]: r["verdict"] for r in out["rows"]}
    assert verd["2026-07"] == "SIN_DATOS"
    assert verd["2026-08"] == "DEGENERADO"
    assert verd["2026-09"] == "ESPERADO_NO_DEFINIDO"
    # el diagnóstico liviano existe siempre y es una línea informativa
    for r in out["rows"]:
        assert r["diagnostico"] and isinstance(r["diagnostico"], str)


# -- expectativas --------------------------------------------------------------
def test_carga_expectativas_desde_archivo(tmp_path):
    exp_file = tmp_path / "exp.json"
    exp_file.write_text(json.dumps(
        {"mi_variante": {"sharpe_mensual": 1.0}}))
    db = str(tmp_path / "v4.db")
    led = SignalLedger(db)
    _seed(led, "m1", "AAA", "2026-07-01", "2026-07-10", -0.20,
          factors={"variant": "mi_variante"})
    _seed(led, "m2", "BBB", "2026-07-05", "2026-07-20", 0.60,
          factors={"variant": "mi_variante"})                     # sharpe=0.707
    rep = MonthlyReporter(db_path=db, expectations_path=str(exp_file))
    out = rep.generate(month="2026-07", persist=False)
    r = out["rows"][0]
    assert r["expected_sharpe_mensual"] == 1.0
    # sharpe 0.707 < umbral 0.5×1.0 → NO calibra contra esta expectativa exigente
    assert r["verdict"] == "DEBAJO_ESPERADO"


def test_archivo_de_expectativas_ausente_usa_semilla(tmp_path):
    rep = _reporter(str(tmp_path / "v5.db"),
                    expectations_path=str(tmp_path / "no_existe.json"))
    assert DEFAULT_VARIANT in rep.expectations
    assert abs(rep.expectations[DEFAULT_VARIANT]["sharpe_mensual"]
               - 0.383816) < 1e-9


# -- bitácora --------------------------------------------------------------------
def test_bitacora_acumula_idempotente(tmp_path):
    db = str(tmp_path / "bit.db")
    led = SignalLedger(db)
    _seed(led, "a1", "AAA", "2026-07-01", "2026-07-10", 0.10)
    _seed(led, "a2", "BBB", "2026-07-05", "2026-07-20", 0.30)
    _seed(led, "b1", "CCC", "2026-08-01", "2026-08-10", -0.10)
    _seed(led, "b2", "DDD", "2026-08-05", "2026-08-20", -0.02)
    rep = _reporter(db)
    rep.generate(month="2026-07")
    rep.generate(month="2026-08")
    rep.generate(month="2026-07")  # regenerar NO duplica (upsert por PK)
    det = rep.months(variant=DEFAULT_VARIANT)
    assert [m["month"] for m in det] == ["2026-07", "2026-08"]
    agg = rep.bitacora()[0]
    assert agg["meses"] == 2
    assert agg["en_calibracion"] == 1 and agg["negativos"] == 1


def test_umbral_calibracion_parametrizable(tmp_path):
    db = str(tmp_path / "umb.db")
    led = SignalLedger(db)
    _seed(led, "u1", "AAA", "2026-07-01", "2026-07-10", -0.10)
    _seed(led, "u2", "BBB", "2026-07-05", "2026-07-20", 0.11)
    # sharpe≈+0.034: DEBAJO con umbral default, EN_CALIBRACION con umbral 0
    out = _reporter(db).generate(month="2026-07", persist=False)["rows"][0]
    assert out["verdict"] == "DEBAJO_ESPERADO"
    out0 = _reporter(db, umbral_calibracion=0.0).generate(
        month="2026-07", persist=False)["rows"][0]
    assert out0["verdict"] == "EN_CALIBRACION"
