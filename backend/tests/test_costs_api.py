"""Tests del contrato /api/costs/current (Tarea E, Ronda 2026-08-19).

Patrón del repo (ver test_advisor_api.py): se llama a la corutina del router
directamente con asyncio.run — el repo no tiene httpx/TestClient en dev-deps.
La DB y el artefacto .txt se reemplazan con fixtures locales (tmp_path):
JAMÁS se toca la red ni la DB real de mediciones.

Contrato validado:
- medido=true con DB: contrato completo + curva por tamaño (lista 'sizes'),
- medido=true con artefacto .txt (fallback si no hay DB),
- medido=false con nota si NO hay ninguna medición — nunca inventar un número.
"""
import json

import pytest
from app.api.routes import costs


def _seed_db(path, records):
    """Crea una DB de mediciones con `records` = [(symbol, side, date, p_dec, p_fill, com, size)]."""
    from app.core.execution_costs import ExecutionCostRecorder

    rec = ExecutionCostRecorder(db_path=str(path))
    try:
        for symbol, side, date, p_dec, p_fill, com, size in records:
            rec.record(symbol, side, date, p_dec, p_fill, com, size)
    finally:
        rec.close()


@pytest.fixture
def sin_db_ni_artefacto(monkeypatch, tmp_path):
    monkeypatch.setattr(costs, "_db_path", lambda: str(tmp_path / "no_existe.db"))
    monkeypatch.setattr(costs, "_latest_artifact_path", lambda: None)
    monkeypatch.setattr(costs, "_cache_dir", lambda: str(tmp_path))


@pytest.fixture
def db_con_qty1(tmp_path):
    path = tmp_path / "execution_costs.db"
    _seed_db(
        path,
        [
            ("SPY", "buy", "2026-08-18", 100.00, 100.01, 0.0, 1.0),
            ("QQQ", "buy", "2026-08-18", 50.00, 50.005, 0.0, 1.0),
            ("SPY", "sell", "2026-08-18", 100.00, 99.99, 0.0, 1.0),
            ("QQQ", "sell", "2026-08-18", 50.00, 49.995, 0.0, 1.0),
        ],
    )
    return path


# --- medido=true desde la DB (registro canónico) ---

def test_current_desde_db(monkeypatch, db_con_qty1):
    monkeypatch.setattr(costs, "_db_path", lambda: str(db_con_qty1))
    monkeypatch.setattr(costs, "_latest_artifact_path", lambda: None)

    body = costs.costs_current()

    assert body["medido"] is True
    assert body["n_ordenes"] == 4
    assert body["fecha_medicion"] == "2026-08-18"
    assert body["ventana"] == "2026-08-18 a 2026-08-18"
    assert body["sizes"][0]["size"] == 1.0
    assert body["sizes"][0]["n_ordenes"] == 4
    # cost_per_side = mean(|slippage|) + mean(comisión):
    # |slips| = [0.0001, 0.0001, 0.0001, 0.0001] -> media 0.0001
    assert body["cost_per_side_medido"] == pytest.approx(0.0001)
    assert body["comision_media"] == 0.0
    # caveat paper siempre presente cuando hay medición
    assert "PAPER" in body["nota"]


def test_curva_por_tamano(monkeypatch, tmp_path):
    """La Tarea D agrega qty=10/50 a la misma DB — el endpoint ya devuelve la curva."""
    path = tmp_path / "curva.db"
    _seed_db(
        path,
        [
            ("SPY", "buy", "2026-08-18", 100.00, 100.01, 0.0, 1.0),
            ("SPY", "buy", "2026-08-19", 100.00, 100.03, 0.0, 10.0),
            ("SPY", "buy", "2026-08-19", 100.00, 100.05, 0.0, 50.0),
        ],
    )
    monkeypatch.setattr(costs, "_db_path", lambda: str(path))
    monkeypatch.setattr(costs, "_latest_artifact_path", lambda: None)

    body = costs.costs_current()

    assert [p["size"] for p in body["sizes"]] == [1.0, 10.0, 50.0]
    assert [p["n_ordenes"] for p in body["sizes"]] == [1, 1, 1]
    assert body["n_ordenes"] == 3
    assert body["fecha_medicion"] == "2026-08-19"
    # el resumen global promedia las tres tallas (0.0001 + 0.0003 + 0.0005) / 3
    assert body["cost_per_side_medido"] == pytest.approx(0.0003)


# --- fallback al artefacto .txt (sin DB) ---

def test_fallback_artefacto_txt(monkeypatch, tmp_path):
    """Sin DB, el endpoint lee el RESUMEN JSON del .txt más reciente."""
    txt = tmp_path / "measure_execution_costs_20260818_134338.txt"
    payload = {
        "cost_per_side_medido": 0.00018883729749502882,
        "n_ordenes": 120,
        "slippage_p50": 0.00012199434031920611,
        "slippage_p95": 0.0005194905531480016,
        "comision_media": 0.0,
        "ventana": "2026-08-18 a 2026-08-18",
    }
    txt.write_text(
        "================================================\n"
        "M4 — medición de costos reales (Alpaca PAPER)\n"
        "RESUMEN (contrato de salida M4):\n"
        f"{json.dumps(payload, indent=2)}\n"
        "================================================\n"
        "ÓRDENES:\n"
    )
    monkeypatch.setattr(costs, "_db_path", lambda: str(tmp_path / "no_existe.db"))
    monkeypatch.setattr(costs, "_latest_artifact_path", lambda: str(txt))

    body = costs.costs_current()

    assert body["medido"] is True
    assert body["cost_per_side_medido"] == pytest.approx(0.00018883729749502882)
    assert body["n_ordenes"] == 120
    assert body["fecha_medicion"] == "2026-08-18"
    assert body["sizes"] == []
    assert "PAPER" in body["nota"]


def test_artefacto_sin_resumen_valido_no_inventa(monkeypatch, tmp_path):
    """Artefacto corrupto o sin bloque JSON -> medido=false, jamás un número."""
    txt = tmp_path / "measure_execution_costs_20260818_134338.txt"
    txt.write_text("no hay JSON acá\nlínea suelta\n")
    monkeypatch.setattr(costs, "_db_path", lambda: str(tmp_path / "no_existe.db"))
    monkeypatch.setattr(costs, "_latest_artifact_path", lambda: str(txt))

    body = costs.costs_current()

    assert body["medido"] is False
    assert body["cost_per_side_medido"] is None


# --- sin ninguna medición ---

def test_sin_medicion_es_honesto(sin_db_ni_artefacto):
    body = costs.costs_current()

    assert body["medido"] is False
    assert body["cost_per_side_medido"] is None
    assert body["slippage_p50"] is None
    assert body["slippage_p95"] is None
    assert body["n_ordenes"] == 0
    assert body["sizes"] == []
    assert "no se inventa" in body["nota"]


# --- robustez: DB corrupta no tira 500 ---

def test_db_corrupta_no_crashea(monkeypatch, tmp_path):
    bad = tmp_path / "execution_costs.db"
    bad.write_bytes(b"esto no es una base sqlite valida" * 10)
    monkeypatch.setattr(costs, "_db_path", lambda: str(bad))
    monkeypatch.setattr(costs, "_latest_artifact_path", lambda: None)

    body = costs.costs_current()

    assert body["medido"] is False
    assert body["cost_per_side_medido"] is None
