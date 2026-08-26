"""Tests para event_pairs.py — construccion de ordenes, NO trades reales.

Verifica:
- Ambas patas (long y short) se ejecutan con el side correcto
- Signal IDs son deterministas
- Ledger recibe qty negativo para pata corta
- P&L se calcula correctamente (inverso para shorts)
- dry-run no ejecuta nada
- Error en una pata no corta la otra (ya registrada)
"""
import datetime as dt
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call, patch

import pytest

from app.core.event_pairs import (
    PairTrade,
    _make_signal_id,
    close_pair,
    open_pair,
    pnl_summary,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class FakeAlpacaClient:
    """Fake que devuelve fills predefinidos sin pegar a la red."""

    def __init__(self, fills: Optional[Dict[str, float]] = None):
        self.fills = fills or {"CAT": 100.0, "TRV": 200.0}
        self.orders: List[Dict[str, Any]] = []

    def submit_market_order(self, symbol: str, qty: float, side: str) -> Dict[str, Any]:
        fill = self.fills.get(symbol, 150.0)
        self.orders.append({"symbol": symbol, "qty": qty, "side": side, "fill": fill})
        return {
            "id": f"order-{symbol}-{side}",
            "status": "filled",
            "filled_avg_price": str(fill),
        }


class FakeLedger:
    """Fake que registra llamadas sin SQLite."""

    def __init__(self):
        self.opened: List[Dict[str, Any]] = []
        self.closed: List[Dict[str, Any]] = []

    def open_order(
        self,
        signal_id: str,
        symbol: str,
        entry_date: str,
        qty: float,
        open_fill_price: float,
        factors: Optional[Dict[str, Any]] = None,
        regime_state: int = 0,
    ) -> None:
        self.opened.append({
            "signal_id": signal_id,
            "symbol": symbol,
            "entry_date": entry_date,
            "qty": qty,
            "open_fill_price": open_fill_price,
            "factors": factors,
        })

    def close_order(
        self,
        signal_id: str,
        exit_date: str,
        exit_reason: str,
        pnl_r: float,
        close_fill_price: Optional[float] = None,
    ) -> None:
        self.closed.append({
            "signal_id": signal_id,
            "exit_date": exit_date,
            "exit_reason": exit_reason,
            "pnl_r": pnl_r,
            "close_fill_price": close_fill_price,
        })


# --------------------------------------------------------------------------- #
# Tests: signal_id
# --------------------------------------------------------------------------- #

def test_make_signal_id_deterministic():
    sid1 = _make_signal_id("CAT", "2026-08-26", "long")
    sid2 = _make_signal_id("CAT", "2026-08-26", "long")
    assert sid1 == sid2
    assert sid1 == "pair_CAT_long_2026-08-26"


def test_make_signal_id_differs_by_side():
    long_sid = _make_signal_id("CAT", "2026-08-26", "long")
    short_sid = _make_signal_id("CAT", "2026-08-26", "short")
    assert long_sid != short_sid


# --------------------------------------------------------------------------- #
# Tests: open_pair
# --------------------------------------------------------------------------- #

def test_open_pair_both_legs_executed():
    client = FakeAlpacaClient(fills={"CAT": 100.0, "TRV": 200.0})
    ledger = FakeLedger()

    trade = open_pair(
        client=client,
        ledger=ledger,
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=5,
        reason="terremoto",
        entry_date="2026-08-26",
    )

    assert trade.error is None
    assert trade.long_fill == 100.0
    assert trade.short_fill == 200.0
    assert len(client.orders) == 2
    assert client.orders[0] == {"symbol": "CAT", "qty": 10, "side": "buy", "fill": 100.0}
    assert client.orders[1] == {"symbol": "TRV", "qty": 5, "side": "sell", "fill": 200.0}


def test_open_pair_ledger_received_both_legs():
    client = FakeAlpacaClient()
    ledger = FakeLedger()

    trade = open_pair(
        client=client,
        ledger=ledger,
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=5,
        reason="test",
        entry_date="2026-08-26",
    )

    assert len(ledger.opened) == 2
    # Long leg
    long_row = ledger.opened[0]
    assert long_row["symbol"] == "CAT"
    assert long_row["qty"] == 10  # positivo para long
    assert long_row["factors"]["leg"] == "long"
    # Short leg
    short_row = ledger.opened[1]
    assert short_row["symbol"] == "TRV"
    assert short_row["qty"] == -5  # negativo para short
    assert short_row["factors"]["leg"] == "short"


def test_open_pair_signal_ids_deterministic():
    client = FakeAlpacaClient()
    ledger = FakeLedger()

    trade = open_pair(
        client=client,
        ledger=ledger,
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=10,
        entry_date="2026-08-26",
    )

    assert trade.long_signal_id == "pair_CAT_long_2026-08-26"
    assert trade.short_signal_id == "pair_TRV_short_2026-08-26"


def test_open_pair_error_on_long_stops_short():
    client = FakeAlpacaClient()
    client.fills["CAT"] = None  # force error
    ledger = FakeLedger()

    # Override to raise on CAT
    def bad_order(symbol, qty, side):
        if symbol == "CAT":
            raise RuntimeError("API timeout")
        return {"id": "ok", "status": "filled", "filled_avg_price": "200.0"}

    client.submit_market_order = bad_order

    trade = open_pair(
        client=client,
        ledger=ledger,
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=10,
        entry_date="2026-08-26",
    )

    assert trade.error is not None
    assert "long_error" in trade.error
    assert len(ledger.opened) == 0  # nothing registered


def test_open_pair_error_on_short_preserves_long():
    client = FakeAlpacaClient()
    ledger = FakeLedger()

    def bad_order(symbol, qty, side):
        if symbol == "TRV":
            raise RuntimeError("short reject")
        return {"id": "ok", "status": "filled", "filled_avg_price": "100.0"}

    client.submit_market_order = bad_order

    trade = open_pair(
        client=client,
        ledger=ledger,
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=10,
        entry_date="2026-08-26",
    )

    assert trade.error is not None
    assert "short_error" in trade.error
    assert len(ledger.opened) == 1  # long was registered
    assert ledger.opened[0]["symbol"] == "CAT"


# --------------------------------------------------------------------------- #
# Tests: close_pair
# --------------------------------------------------------------------------- #

def test_close_pair_both_legs_closed():
    # Open with one set of fills, close with different fills (price moved)
    client_open = FakeAlpacaClient(fills={"CAT": 100.0, "TRV": 200.0})
    client_close = FakeAlpacaClient(fills={"CAT": 110.0, "TRV": 190.0})
    ledger = FakeLedger()

    # First open (CAT bought at 100, TRV sold at 200)
    trade = open_pair(
        client=client_open,
        ledger=ledger,
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=10,
        entry_date="2026-08-26",
    )

    # Close (CAT sold at 110, TRV bought back at 190)
    trade = close_pair(
        client=client_close,
        ledger=ledger,
        trade=trade,
        exit_date="2026-08-27",
    )

    assert trade.error is None
    assert len(ledger.closed) == 2
    # Long P&L: (110 * 0.999) / (100 * 1.001) - 1 = ~+0.0978
    long_pnl = ledger.closed[0]["pnl_r"]
    assert long_pnl > 0  # profit
    # Short P&L: (200 * 0.999) / (190 * 1.001) - 1 = ~+0.0516
    short_pnl = ledger.closed[1]["pnl_r"]
    assert short_pnl > 0  # profit (price dropped)


def test_close_pair_short_pnl_inverted():
    """Short leg P&L is inverted: profit when price drops."""
    client = FakeAlpacaClient(fills={"TRV": 180.0})  # exit lower
    ledger = FakeLedger()

    # Manually create a trade
    trade = PairTrade(
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=10,
        entry_date="2026-08-26",
        long_fill=100.0,
        short_fill=200.0,
        long_signal_id="pair_CAT_long_2026-08-26",
        short_signal_id="pair_TRV_short_2026-08-26",
    )

    trade = close_pair(
        client=client,
        ledger=ledger,
        trade=trade,
        exit_date="2026-08-27",
    )

    # Short profit: sold at 200, bought back at 180
    short_pnl = ledger.closed[1]["pnl_r"]
    assert short_pnl > 0


# --------------------------------------------------------------------------- #
# Tests: pnl_summary
# --------------------------------------------------------------------------- #

def test_pnl_summary_complete_trade():
    trade = PairTrade(
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=5,
        entry_date="2026-08-26",
        long_fill=100.0,
        short_fill=200.0,
        reason="terremoto",
    )

    summary = pnl_summary(trade)

    assert summary["long_notional"] == 1000.0
    assert summary["short_notional"] == 1000.0
    assert summary["net_exposure"] == 0.0  # market-neutral


def test_pnl_summary_incomplete_trade():
    trade = PairTrade(
        symbol_long="CAT",
        symbol_short="TRV",
        qty_long=10,
        qty_short=10,
        entry_date="2026-08-26",
    )

    summary = pnl_summary(trade)
    assert "error" in summary


# --------------------------------------------------------------------------- #
# Tests: dry-run (CLI)
# --------------------------------------------------------------------------- #

def test_dry_run_no_side_effects(capsys):
    from app.core.event_pairs import main

    rc = main(["--long", "CAT", "--short", "TRV", "--qty", "10", "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out
    assert "No se ejecuta nada" in captured.out
