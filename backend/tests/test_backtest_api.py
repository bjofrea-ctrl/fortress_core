"""Tests de integración del router /api/backtest (lee data/backtest_results.json).

Se testea el contrato de cada endpoint con datos sintéticos; el archivo se
apunta a un tmp_path vía monkeypatch (nunca al estado de runtime real).
"""
import asyncio
import json

import pytest
from app.api.routes import backtest


@pytest.fixture
def results_file(tmp_path):
    """Escribe un backtest_results.json sintético y devuelve su path."""
    data = {
        "metrics": {"total_return_pct": 12.5, "sharpe": 1.2, "max_drawdown_pct": -8.0},
        "equity_curve": [
            {"date": "2024-01-02", "equity": 100000.0, "drawdown_pct": 0.0},
            {"date": "2024-01-03", "equity": 101200.0, "drawdown_pct": -0.5},
        ],
        "trades": [
            {"symbol": "TESTA", "entry_date": "2024-01-02", "exit_date": "2024-01-10",
             "entry_price": 100.0, "exit_price": 105.5, "shares": 10, "pnl": 55.0,
             "exit_reason": "take_profit"},
            {"symbol": "TESTB", "entry_date": "2024-01-05", "exit_date": "2024-01-12",
             "entry_price": 50.0, "exit_price": 48.0, "shares": 10, "pnl": -20.0,
             "exit_reason": "stop_loss"},
        ],
        "monte_carlo": {"n_sims": 100, "p95": 95000.0, "p5": 120000.0},
    }
    path = tmp_path / "backtest_results.json"
    path.write_text(json.dumps(data))
    return str(path)


def _set_file(monkeypatch, path):
    monkeypatch.setattr(backtest, "RESULTS_FILE", path)


def test_results_sin_archivo(monkeypatch, tmp_path):
    _set_file(monkeypatch, str(tmp_path / "no_existe.json"))
    body = asyncio.run(backtest.get_backtest_results())
    assert body["status"] == "no_data"


def test_results_devuelve_el_archivo(monkeypatch, results_file):
    _set_file(monkeypatch, results_file)
    body = asyncio.run(backtest.get_backtest_results())
    assert body["metrics"]["total_return_pct"] == 12.5


def test_metrics_sin_archivo(monkeypatch, tmp_path):
    _set_file(monkeypatch, str(tmp_path / "no_existe.json"))
    assert asyncio.run(backtest.get_backtest_metrics()) == {"status": "no_data"}


def test_metrics_devuelve_solo_metrics(monkeypatch, results_file):
    _set_file(monkeypatch, results_file)
    body = asyncio.run(backtest.get_backtest_metrics())
    assert set(body) == {"total_return_pct", "sharpe", "max_drawdown_pct"}


def test_equity_curve_formatea_fechas_str(monkeypatch, results_file):
    _set_file(monkeypatch, results_file)
    body = asyncio.run(backtest.get_equity_curve())
    assert body["equity_curve"][0] == {"date": "2024-01-02", "equity": 100000.0, "drawdown": 0.0}


def test_equity_curve_muestrea_a_300(monkeypatch, tmp_path):
    points = [
        {"date": "2024-01-02", "equity": 100000 + i, "drawdown_pct": -0.01}
        for i in range(350)
    ]
    path = tmp_path / "muchos.json"
    path.write_text(json.dumps({"equity_curve": points, "metrics": {}}))
    _set_file(monkeypatch, str(path))

    body = asyncio.run(backtest.get_equity_curve())
    assert len(body["equity_curve"]) <= 300
    assert all("date" in p and "equity" in p and "drawdown" in p for p in body["equity_curve"])


def test_trades_limita_a_50(monkeypatch, tmp_path):
    trades = [
        {"symbol": f"T{i}", "entry_date": "2024-01-01", "exit_date": "2024-01-02",
         "entry_price": 10.0, "exit_price": 11.0, "shares": 1, "pnl": 1.0,
         "exit_reason": "x"}
        for i in range(60)
    ]
    path = tmp_path / "trades.json"
    path.write_text(json.dumps({"trades": trades, "metrics": {}}))
    _set_file(monkeypatch, str(path))

    body = asyncio.run(backtest.get_trades())
    assert len(body["trades"]) == 50
    assert body["total"] == 60


def test_monte_carlo(monkeypatch, results_file):
    _set_file(monkeypatch, results_file)
    body = asyncio.run(backtest.get_monte_carlo())
    assert body["n_sims"] == 100
