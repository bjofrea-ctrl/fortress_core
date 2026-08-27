"""
Tests del conector PAPER TRADING (Frente 2, Semana 1).

Cubren, siempre contra fakes (jamás red):
- lectura de cuenta/posiciones (GET /v2/account, /v2/positions) — AlpacaPaperClient;
- ciclo de vida del signal_ledger (open -> closed con pnl_r) — migración aditiva
  que NO rompe el record() T1.6 existente con una DB pre-migrada;
- PaperTrader: abrir orden registra fila open; cerrar completa pnl_r;
  reconcile cierra contra el estado real del papel.
"""
import sqlite3

from app.core.execution_costs import AlpacaPaperClient
from app.core.paper_trading import PaperTrader
from app.core.signal_ledger import SignalLedger


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    """Sesión fake del paper: account, positions, trades/latest, órdenes con
    fill que llega por polling (como el Alpaca real: pending -> filled)."""

    def __init__(self, account=None, positions=None, prices=None, fill_price=100.0):
        self.headers = {}
        self.account = account or {"cash": "1000.0", "equity": "1000.0",
                                   "buying_power": "2000.0"}
        self.positions = positions or []
        self.prices = prices or {"AAA": 100.0}
        self.fill_price = fill_price  # precio de fill de las órdenes (fixed)
        self.orders = {}
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        sym = json["symbol"]
        oid = f"oid-{len(self.orders) + 1}"
        self.orders[oid] = {"id": oid, "symbol": sym, "qty": json["qty"],
                            "side": json["side"], "status": "pending_new",
                            "filled_avg_price": None,
                            "submitted_at": "2026-08-25T10:00:00Z"}
        return _FakeResp(self.orders[oid])

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        if "/v2/account" in url:
            return _FakeResp(self.account)
        if "/v2/positions" in url:
            return _FakeResp(self.positions)
        if "/v2/orders/" in url:
            oid = url.rstrip("/").split("/")[-1]
            order = dict(self.orders[oid])
            if order["status"] != "filled":
                order["status"] = "filled"
                order["filled_avg_price"] = self.fill_price
                self.orders[oid] = order
            return _FakeResp(order)
        if "/stocks/" in url:  # last trade
            sym = url.split("/stocks/")[1].split("/")[0]
            return _FakeResp({"trade": {"p": self.prices.get(sym.replace(".", "-"), 100.0)}})
        raise AssertionError(f"URL no esperada: {url}")


def _make(fake):
    return AlpacaPaperClient(
        api_key="k", secret_key="s",
        base_url="https://paper-api.alpaca.markets",
        market_data_base_url="https://data.alpaca.markets",
        session=fake)


# a) lectura de cuenta/posiciones ------------------------------------------
def test_get_account_y_posiciones():
    fake = _FakeSession(positions=[{"symbol": "BRK.B", "qty": "10",
                                    "avg_entry_price": "100.0",
                                    "current_price": "110.0",
                                    "market_value": "1100.0"}])
    client = _make(fake)
    acct = client.get_account()
    assert acct["cash"] == "1000.0"
    assert "equity" in acct and "buying_power" in acct
    pos = client.get_positions()
    assert len(pos) == 1
    assert pos[0]["symbol"] == "BRK-B"  # . de Alpaca -> guion interno


# b) lifecycle del ledger + migración aditiva --------------------------------
def test_signal_ledger_open_close_lifecycle(tmp_path):
    led = SignalLedger(str(tmp_path / "ledger.db"))
    led.open_order(signal_id="ord-1", symbol="AAA", entry_date="2026-08-25",
                   qty=10, open_fill_price=100.0, regime_state=0)
    row = led.open_orders()[0]
    assert row["status"] == "open"
    assert row["pnl_r"] == 0.0
    led.close_order(signal_id="ord-1", exit_date="2026-08-26",
                    exit_reason="TARGET", pnl_r=0.10, close_fill_price=110.0)
    closed = led.fetch(symbol="AAA")[0]
    assert closed["status"] == "closed"
# c) PaperTrader: abrir -> fila open; cerrar -> pnl_r; reconcile -------------
def test_papertrader_abre_y_cierra(tmp_path):
    fake = _FakeSession(prices={"AAA": 100.0}, positions=[])
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "pt.db"))
    pt = PaperTrader(client, ledger)

    order = pt.open_paper_order("ord-1", "AAA", 10, "buy", entry_date="2026-08-25")
    assert order["status"] == "filled"
    o = ledger.open_orders()[0]
    assert o["signal_id"] == "ord-1" and o["open_fill_price"] == 100.0

    pnl = pt.close_paper_order("ord-1", "AAA", 10, exit_date="2026-08-26",
                               exit_reason="TP", close_price=110.0)
    assert abs(pnl - 0.10) < 1e-9
    closed = ledger.fetch(symbol="AAA")[0]
    assert closed["status"] == "closed" and closed["close_fill_price"] == 110.0
    assert ledger.count() == 1


def test_papertrader_cierra_sin_precio_con_last_trade(tmp_path):
    fake = _FakeSession(prices={"AAA": 105.0}, positions=[])
    client = _make(fake)
    pt = PaperTrader(client, SignalLedger(str(tmp_path / "pt2.db")))
    pt.open_paper_order("ord-2", "AAA", 10, "buy", entry_date="2026-08-25")
    # cierre sin pasar close_price -> usa last_trade_price 105
    pnl = pt.close_paper_order("ord-2", "AAA", 10, exit_date="2026-08-26",
                               exit_reason="TP")
    assert abs(pnl - 0.05) < 1e-9


def test_papertrader_reconcile_cierra_posicion_desaparecida(tmp_path):
    fake = _FakeSession(positions=[], prices={"AAA": 90.0})
    client = _make(fake)
    pt = PaperTrader(client, SignalLedger(str(tmp_path / "rec.db")))
    pt.open_paper_order("rec-1", "AAA", 5, "buy")
    n = pt.reconcile_open_positions(exit_date="2026-08-26", exit_reason="RECONCILE")
    assert n == 1
    closed = pt.ledger.fetch()[0]
    assert closed["status"] == "closed"
    # el precio de cierre contable es el último trade (90); el pnl_r registrado
    # es el pendiente de la fila (0.0 hasta el cierre real)
    assert closed["close_fill_price"] == 90.0
    assert closed["pnl_r"] == 0.0
    assert pt.ledger.open_orders() == []


def test_signal_ledger_old_api_no_rompe_con_db_premigrada(tmp_path):
    """La migración aditiva no rompe el record() (T1.6) sobre una db vieja."""
    db = str(tmp_path / "pre.db")
    _SCHEMA_OLD = """
    CREATE TABLE signal_ledger (
        signal_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
        entry_date DATE NOT NULL, exit_date DATE NOT NULL,
        exit_reason TEXT NOT NULL, pnl_r REAL NOT NULL,
        factors_json TEXT NOT NULL, regime_state INTEGER NOT NULL)
    """
    with sqlite3.connect(db) as conn:
        conn.execute(_SCHEMA_OLD)
        conn.execute("INSERT INTO signal_ledger VALUES ('old', 'AAA', '2026-01-01',"
                     "'2026-01-02', 'WIN', 0.05, '{}', 0)")
    led = SignalLedger(db)  # migra aditivamente
    led.record(signal_id="new", symbol="BBB", entry_date="2026-02-01",
               exit_date="2026-02-02", exit_reason="WIN", pnl_r=0.1)
    rows = led.fetch()
    assert len(rows) == 2
    old = [r for r in rows if r["signal_id"] == "old"][0]
    assert old["pnl_r"] == 0.05 and old["status"] == "pending"
    assert old["open_fill_price"] is None
