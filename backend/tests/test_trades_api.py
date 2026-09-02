"""Tests de integración del router /api/trades/combined (backtest + paper ledger).

Verifica el contrato unificado: cada fila lleva `origin` explícito
('backtest' | 'paper'), se sirven TODOS los trades del backtest (sin límite 50)
y las filas paper se leen de signal_ledger con sus fills. Nunca toca el estado
de runtime real: RESULTS_FILE y LEDGER_DB se apuntan a tmp_path.
"""
import asyncio
import json
import sqlite3

import pytest
from app.api.routes import trades


@pytest.fixture
def results_file(tmp_path):
    """Escribe un backtest_results.json sintético con 60 trades (más que el
    viejo límite de 50) y devuelve su path."""
    trades_list = [
        {"symbol": f"T{i}", "entry_date": "2023-01-01",
         "exit_date": "2023-02-01", "entry_price": 10.0, "exit_price": 11.0,
         "shares": 1, "pnl": 1.0, "exit_reason": "x"}
        for i in range(60)
    ]
    # asegurar fechas estrictamente crecientes para el orden descendente
    for i, t in enumerate(trades_list):
        t["entry_date"] = f"2023-{(i // 28) + 1:02d}-{i % 28 + 1:02d}"
    path = tmp_path / "backtest_results.json"
    path.write_text(json.dumps({"trades": trades_list, "metrics": {}}))
    return str(path)


@pytest.fixture
def ledger_db(tmp_path):
    """Crea una fortress.db temporal con signal_ledger sembrado (open + closed)."""
    db = str(tmp_path / "fortress.db")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE signal_ledger (
            signal_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
            entry_date DATE NOT NULL, exit_date DATE NOT NULL,
            exit_reason TEXT NOT NULL, pnl_r REAL NOT NULL,
            factors_json TEXT NOT NULL, regime_state INTEGER NOT NULL,
            status TEXT NOT NULL, open_fill_price REAL,
            close_fill_price REAL, qty REAL
        )
    """)
    conn.execute("""
        INSERT INTO signal_ledger VALUES
        ('p1','AAPL','2026-08-25','2026-08-28','TAKE_PROFIT',0.0432,'{}',0,
         'closed',185.4,193.4,10),
        ('p2','NVDA','2026-08-26','2026-08-26','TRAILING',-0.012,'{}',2,
         'closed',128.7,127.15,5),
        ('p3','MSFT','2026-08-27','2026-08-27','OPEN',0.0,'{}',0,
         'open',430.1,NULL,8)
    """)
    conn.commit()
    conn.close()
    return db


def _setup(monkeypatch, results_file, ledger_db):
    monkeypatch.setattr(trades, "RESULTS_FILE", results_file)
    monkeypatch.setattr(trades, "LEDGER_DB", ledger_db)


def test_sin_archivo_ni_db(monkeypatch, tmp_path):
    monkeypatch.setattr(trades, "RESULTS_FILE", str(tmp_path / "no.json"))
    monkeypatch.setattr(trades, "LEDGER_DB", str(tmp_path / "no.db"))
    body = asyncio.run(trades.get_combined_trades())
    assert body == {"trades": [], "total": 0, "backtest_total": 0, "paper_total": 0}


def test_sirve_todos_los_trades_backtest_sin_limite_50(monkeypatch, results_file, tmp_path):
    _setup(monkeypatch, results_file, str(tmp_path / "no.db"))  # sin ledger
    body = asyncio.run(trades.get_combined_trades(limit=0))
    assert body["backtest_total"] == 60
    assert len(body["trades"]) == 60  # el viejo /trades cortaba en 50
    assert body["paper_total"] == 0
    assert all(t["origin"] == "backtest" for t in body["trades"])
    assert all(t["status"] == "closed" for t in body["trades"])


def test_combina_paper_y_backtest_con_origin_explicito(monkeypatch, results_file, ledger_db):
    _setup(monkeypatch, results_file, ledger_db)
    body = asyncio.run(trades.get_combined_trades(limit=0))
    assert body["backtest_total"] == 60
    assert body["paper_total"] == 3
    assert body["total"] == 63
    origins = {t["origin"] for t in body["trades"]}
    assert origins == {"backtest", "paper"}


def test_orden_descendente_por_entry_date(monkeypatch, results_file, ledger_db):
    _setup(monkeypatch, results_file, ledger_db)
    body = asyncio.run(trades.get_combined_trades(limit=0))
    dates = [t["entry_date"] for t in body["trades"] if t["entry_date"]]
    assert dates == sorted(dates, reverse=True)


def test_paper_cerrado_trae_fills_y_pnl(monkeypatch, results_file, ledger_db):
    _setup(monkeypatch, results_file, ledger_db)
    body = asyncio.run(trades.get_combined_trades(limit=0))
    closed = [t for t in body["trades"] if t["signal_id"] == "p1"][0]
    assert closed["origin"] == "paper"
    assert closed["exit_price"] == 193.4
    assert closed["pnl"] == 80.0      # qty 10 * (193.4 - 185.4)
    assert closed["pnl_r"] == 0.0432


def test_paper_abierto_no_fabrica_pnl_ficticio(monkeypatch, results_file, ledger_db):
    _setup(monkeypatch, results_file, ledger_db)
    body = asyncio.run(trades.get_combined_trades(limit=0))
    opened = [t for t in body["trades"] if t["signal_id"] == "p3"][0]
    assert opened["status"] == "open"
    assert opened["exit_price"] is None
    assert opened["pnl"] is None
    assert opened["pnl_r"] is None


def test_paginacion_default_y_skip(monkeypatch, results_file, ledger_db):
    _setup(monkeypatch, results_file, ledger_db)
    # default limit 200 alcanza para los 63
    body = asyncio.run(trades.get_combined_trades())
    assert len(body["trades"]) == 63
    assert body["total"] == 63
    # limit=10 devuelve exactamente 10 (los 3 paper + 7 backtest recientes)
    body2 = asyncio.run(trades.get_combined_trades(limit=10))
    assert len(body2["trades"]) == 10
    # limit=0 = "todos" (ignora skip por contrato)
    body3 = asyncio.run(trades.get_combined_trades(skip=3, limit=0))
    assert len(body3["trades"]) == 63
    # skip=3 con limit acotado: salta los 3 paper
    body4 = asyncio.run(trades.get_combined_trades(skip=3, limit=200))
    assert len(body4["trades"]) == 60
    assert all(t["origin"] == "backtest" for t in body4["trades"])


def test_ledger_sin_tabla_devuelve_solo_backtest(monkeypatch, results_file, tmp_path):
    # DB existe pero sin tabla signal_ledger (estado real hoy: pipeline dry-run)
    db = str(tmp_path / "vacia.db")
    sqlite3.connect(db).close()
    _setup(monkeypatch, results_file, db)
    body = asyncio.run(trades.get_combined_trades(limit=0))
    assert body["paper_total"] == 0
    assert body["backtest_total"] == 60
    assert all(t["origin"] == "backtest" for t in body["trades"])
