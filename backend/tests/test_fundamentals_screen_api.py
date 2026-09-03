"""
Tests del router /api/fundamentals/* (Fase 4).

Patrón del repo (ver test_advisor_api.py / test_costs_api.py): se llama a
la corutina del router directamente con asyncio.run — el repo no tiene
httpx/TestClient en dev-deps. Cero red: los artefactos en disco se
crean con fixtures locales (tmp_path).

Contrato validado:
- /screen/latest  → 503 cuando no hay screenings; 200 con el último
- /screen?date=   → 404 si no hay artefacto; 422 si formato inválido; 200 con el screening
- /screen/state   → 200 con "never_run" o con el state.json
- /screen/dashboard.html → 503 sin HTML; 200 con el HTML
- _list_available_dates() filtra prefijos correctamente
"""
import asyncio
import json
from pathlib import Path

import pytest

from app.api.routes import fundamentals_screen


# ============================================================================
# Router — sólo-lectura, no toca red. Patrón del repo (test_advisor_api.py):
# se llama a la corutina del router directamente con asyncio.run.
# ============================================================================

def test_router_latest_503_when_no_screenings(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    with pytest.raises(Exception) as exc_info:
        asyncio.run(fundamentals_screen.get_screen_latest())
    # HTTPException tiene .status_code y .detail
    assert exc_info.value.status_code == 503
    assert "No hay screenings" in exc_info.value.detail


def test_router_latest_returns_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    for date, baldes in [("2026-08-26", {"DD": 5}), ("2026-08-27", {"DD": 13})]:
        Path(tmp_path, f"screen_{date}.json").write_text(
            json.dumps({"date": date, "baldes": baldes})
        )
    result = asyncio.run(fundamentals_screen.get_screen_latest())
    assert result["date"] == "2026-08-27"
    assert result["baldes"] == {"DD": 13}


def test_router_by_date_404_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    with pytest.raises(Exception) as exc_info:
        asyncio.run(fundamentals_screen.get_screen_by_date(date="2026-08-27"))
    assert exc_info.value.status_code == 404
    assert "2026-08-27" in exc_info.value.detail


def test_router_by_date_validates_format(tmp_path, monkeypatch):
    """Fecha con formato inválido → 422. La validación la hace la función
    mismo con _DATE_RE (FastAPI valida via Query(pattern=...), pero cuando
    el test llama directo con asyncio.run saltamos FastAPI y validamos acá)."""
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    with pytest.raises(Exception) as exc_info:
        asyncio.run(fundamentals_screen.get_screen_by_date(date="27-08-2026"))
    assert exc_info.value.status_code == 422
    assert "YYYY-MM-DD" in exc_info.value.detail


def test_router_by_date_returns_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    Path(tmp_path, "screen_2026-08-27.json").write_text(
        json.dumps({"date": "2026-08-27", "results": {"AAPL": {"balde": "Deep Dive"}}})
    )
    result = asyncio.run(fundamentals_screen.get_screen_by_date(date="2026-08-27"))
    assert result["results"]["AAPL"]["balde"] == "Deep Dive"


def test_router_state_never_run(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    result = asyncio.run(fundamentals_screen.get_state())
    assert result["status"] == "never_run"


def test_router_state_returns_state_json(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    state = {"last_run_finished": "2026-08-27T22:35:00Z", "calls_used": 240,
             "completed_symbols": ["AAPL", "MSFT"], "failed_symbols": []}
    Path(tmp_path, "state.json").write_text(json.dumps(state))
    result = asyncio.run(fundamentals_screen.get_state())
    assert result["calls_used"] == 240


def test_router_dashboard_html_503_when_no_html(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    with pytest.raises(Exception) as exc_info:
        asyncio.run(fundamentals_screen.get_dashboard_html())
    assert exc_info.value.status_code == 503


def test_router_dashboard_html_serves_html(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    Path(tmp_path, "dashboard_2026-08-27.html").write_text(
        "<!DOCTYPE html><html><body>Test</body></html>"
    )
    # get_dashboard_html devuelve un HTMLResponse (no string). El body
    # se accede vía .body.
    result = asyncio.run(fundamentals_screen.get_dashboard_html(date="2026-08-27"))
    assert "<html>" in result.body.decode("utf-8")
    assert "text/html" in result.media_type


def test_router_list_dates_filters_prefixes(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    Path(tmp_path, "screen_2026-08-27.json").write_text("{}")
    Path(tmp_path, "dashboard_2026-08-27.html").write_text("<html></html>")
    Path(tmp_path, "state.json").write_text("{}")
    Path(tmp_path, "unrelated.txt").write_text("foo")
    dates = fundamentals_screen._list_available_dates()
    assert dates == ["2026-08-27"]


def test_router_list_dates_returns_desc_sorted(tmp_path, monkeypatch):
    monkeypatch.setattr(fundamentals_screen, "_CACHE_DIR", str(tmp_path))
    for d in ["2026-08-25", "2026-08-27", "2026-08-26"]:
        Path(tmp_path, f"screen_{d}.json").write_text("{}")
    dates = fundamentals_screen._list_available_dates()
    assert dates == ["2026-08-27", "2026-08-26", "2026-08-25"]