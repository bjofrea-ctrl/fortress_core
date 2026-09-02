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
    # precio de cierre contable es last_trade 90; pnl real (90-100)/100 = -0.10 (fix F0)
    assert closed["close_fill_price"] == 90.0
    assert abs(closed["pnl_r"] - (-0.10)) < 1e-9
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


# F0 — fixes de auditoría ----------------------------------------------------

def test_reconcile_calcula_pnl_real_no_pisa_con_cero(tmp_path):
    """F0.1: reconcile debe calcular (cp-open)/open, no pisar con 0.0."""
    fake = _FakeSession(positions=[], prices={"AAA": 120.0}, fill_price=100.0)
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "f0a.db"))
    pt = PaperTrader(client, ledger)
    pt.open_paper_order("f0-1", "AAA", 10, "buy", entry_date="2026-08-25")
    n = pt.reconcile_open_positions(exit_date="2026-08-26", exit_reason="RECONCILE")
    assert n == 1
    closed = ledger.fetch()[0]
    # (120-100)/100 = 0.20, no 0.0
    assert abs(closed["pnl_r"] - 0.20) < 1e-9
    assert closed["close_fill_price"] == 120.0


def test_reconcile_fallback_sin_precio_loguea_y_cero(tmp_path, capsys):
    """F0.1 fallback: sin precio de mercado, pnl 0.0 y log."""
    class _NoPriceSession(_FakeSession):
        def get(self, url, timeout=None):
            if "/stocks/" in url:
                raise RuntimeError("no market data")
            return super().get(url, timeout)

    fake = _NoPriceSession(positions=[], prices={}, fill_price=100.0)
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "f0b.db"))
    pt = PaperTrader(client, ledger)
    pt.open_paper_order("f0-2", "AAA", 5, "buy")
    n = pt.reconcile_open_positions(exit_date="2026-08-26")
    assert n == 1
    closed = ledger.fetch()[0]
    assert closed["pnl_r"] == 0.0
    assert closed["close_fill_price"] is None
    err = capsys.readouterr().err
    assert "PRECIOS" not in err  # reconcile loguea con [paper_trading] reconcile
    assert "reconcile" in err.lower() and "sin precio" in err.lower()


def test_close_usa_fill_real_si_se_pasa(tmp_path):
    """F0.2: close con close_price provisto usa ese fill, no last_trade."""
    fake = _FakeSession(prices={"AAA": 999.0}, fill_price=100.0)
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "f0c.db"))
    pt = PaperTrader(client, ledger)
    pt.open_paper_order("f0-3", "AAA", 10, "buy")
    # close_price 115 es fill real, debe usarse aunque last_trade sea 999
    pnl = pt.close_paper_order("f0-3", "AAA", 10, exit_date="2026-08-26", exit_reason="TP", close_price=115.0)
    assert abs(pnl - 0.15) < 1e-9
    closed = ledger.fetch()[0]
    assert closed["close_fill_price"] == 115.0


def test_close_sin_fill_usa_aproximacion_y_documenta(tmp_path, capsys):
    """F0.2: sin close_price usa last_trade como aproximación y lo documenta."""
    fake = _FakeSession(prices={"AAA": 110.0}, fill_price=100.0)
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "f0d.db"))
    pt = PaperTrader(client, ledger)
    pt.open_paper_order("f0-4", "AAA", 10, "buy")
    pnl = pt.close_paper_order("f0-4", "AAA", 10, exit_date="2026-08-26", exit_reason="TP")
    # docstring debe decir aproximación
    assert "aproximación" in PaperTrader.close_paper_order.__doc__
    # debe marcar exit_reason con APPROX
    closed = ledger.fetch()[0]
    assert "APPROX" in closed["exit_reason"]
    assert abs(pnl - 0.10) < 1e-9
    err = capsys.readouterr().err
    assert "aproximación" in err.lower()


def test_open_fill_parcial_loguea_y_ajusta_qty(tmp_path, capsys):
    """F0.3: fill parcial (filled_qty != qty) se loguea y qty se ajusta."""
    class _PartialSession(_FakeSession):
        def get(self, url, timeout=None):
            if "/v2/orders/" in url:
                oid = url.rstrip("/").split("/")[-1]
                order = dict(self.orders[oid])
                if order["status"] != "filled":
                    order["status"] = "filled"
                    order["filled_avg_price"] = self.fill_price
                    order["filled_qty"] = "5"  # parcial: pedimos 10, fill 5
                    order["qty"] = "10"
                    self.orders[oid] = order
                return _FakeResp(order)
            return super().get(url, timeout)

    fake = _PartialSession(prices={"AAA": 100.0}, fill_price=100.0)
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "f0e.db"))
    pt = PaperTrader(client, ledger)
    order = pt.open_paper_order("f0-5", "AAA", 10, "buy")
    assert order["filled_qty"] == "5"
    err = capsys.readouterr().err
    assert "parcial" in err.lower()
    row = ledger.open_orders()[0]
    assert abs(row["qty"] - 5.0) < 1e-9


def test_open_rechazo_no_silencioso(tmp_path, capsys):
    """F0.3: rechazo no queda silencioso — se loguea y propaga."""
    class _RejectSession(_FakeSession):
        def post(self, url, json=None, timeout=None):
            if "/v2/orders" in url:
                raise RuntimeError("Orden AAA buy terminó rejected sin fill: no se registra.")
            return super().post(url, json, timeout)

    fake = _RejectSession()
    client = _make(fake)
    ledger = SignalLedger(str(tmp_path / "f0f.db"))
    pt = PaperTrader(client, ledger)
    try:
        pt.open_paper_order("f0-6", "AAA", 10, "buy")
        assert False, "debió levantar"
    except RuntimeError as exc:
        assert "rejected" in str(exc).lower()
    err = capsys.readouterr().err
    assert "REJECTED" in err or "rejected" in err.lower()
    assert ledger.open_orders() == []
