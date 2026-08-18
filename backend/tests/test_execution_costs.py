"""Tests de M4 — costos medidos (app/core/execution_costs.py).

El test que más importa acá NO es "el código corre" — es que la medición se puede
verificar con un fake del cliente de Alpaca, sin pegar a la red, y que el contrato de
salida sale exactamente como lo especifica ORDENES_MODULOS.md M4. La API se mockea
siempre: jamás una orden real ni en paper desde los tests.
"""
import numpy as np
import pytest
from app.core.execution_costs import (
    AlpacaPaperClient,
    ConfigurationError,
    ExecutionCostRecorder,
    measure_slippage,
    summarize,
)

BASE_URL = "https://paper-api.alpaca.markets"


# --------------------------------------------------------------------------- #
# Fakes — la API se simula, no se toca la red.
# --------------------------------------------------------------------------- #
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
    """Sesión fake: get() devuelve el último trade o el estado de una orden enviada,
    post() crea la orden. Emula el paper real: el fill llega por polling, no en la
    respuesta del envío (status `pending_new` → `filled`)."""

    def __init__(self, prices, fill_mult=1.001, order_status=200, filled=True,
                 pending_polls=0):
        self.headers = {}
        self.prices = prices
        self.fill_mult = fill_mult
        self.order_status = order_status
        self.filled = filled
        self.pending_polls = pending_polls  # polls en que la orden sigue pendiente
        self.get_calls = []
        self.post_calls = []
        self.orders = {}
        self.closed = False

    def _order_state(self, oid):
        """Snapshot de la orden: si le quedan polls pendientes, sigue pendiente;
        si no, ya está filled (como el paper real tras unos segundos)."""
        stored = self.orders[oid]
        remaining = stored.get("_pending_polls", 0)
        order = dict(stored)
        order.pop("_pending_polls", None)
        if remaining > 0:
            stored["_pending_polls"] = remaining - 1
            order["status"] = "pending_new"
            order["filled_avg_price"] = None
        else:
            order["status"] = "filled"
        return order

    def get(self, url, timeout=None):
        self.get_calls.append(url)
        if "/v2/orders/" in url:  # polling del estado de una orden enviada
            oid = url.rstrip("/").split("/")[-1]
            return _FakeResp(self._order_state(oid))
        # endpoint de datos: /v2/stocks/<SYM>/trades/latest
        sym = url.split("/stocks/")[1].split("/")[0]
        return _FakeResp({"trade": {"p": self.prices[sym]}})

    def post(self, url, json=None, timeout=None):
        self.post_calls.append((url, json))
        if self.order_status >= 400:
            return _FakeResp({}, status=self.order_status)
        oid = f"oid-{len(self.orders) + 1}"
        if self.filled:
            order = {
                "id": oid,
                "symbol": json["symbol"],
                "status": "pending_new" if self.pending_polls else "filled",
                "filled_avg_price": self.prices[json["symbol"]] * self.fill_mult,
                "commission": 0.0,
            }
            if self.pending_polls:
                order["_pending_polls"] = self.pending_polls
        else:
            order = {"id": oid, "symbol": json["symbol"], "status": "rejected",
                     "filled_avg_price": None, "commission": 0.0}
        self.orders[oid] = order
        return _FakeResp(dict(order))

    def close(self):
        self.closed = True


class FakeMeasurementClient:
    """Cliente de medición inyectable — misma interfaz que AlpacaPaperClient."""

    def __init__(self, prices, fill_mult=1.001, commission=0.0):
        self.prices = prices
        self.fill_mult = fill_mult
        self.commission = commission
        self.submitted = []

    def last_trade_price(self, symbol):
        return self.prices[symbol]

    def submit_market_order(self, symbol, qty, side):
        fill = self.prices[symbol] * self.fill_mult
        self.submitted.append((symbol, qty, side))
        return {
            "symbol": symbol,
            "filled_avg_price": fill,
            "status": "filled",
            "commission": self.commission * fill * qty if self.commission else 0.0,
        }


PRICES = {"SPY": 500.0, "QQQ": 400.0, "AAPL": 200.0}
# --------------------------------------------------------------------------- #
# measure_slippage — conductor con cliente inyectado.
# --------------------------------------------------------------------------- #
def test_measure_slippage_calcula_y_persiste(tmp_path):
    db = tmp_path / "costs.db"
    client = FakeMeasurementClient(PRICES, fill_mult=1.01)  # slippage 1%
    r = ExecutionCostRecorder(str(db))
    try:
        measured = measure_slippage(client, r, ["SPY", "QQQ"])
    finally:
        r.close()
    assert len(measured) == 2
    assert measured[0].symbol == "SPY"
    assert measured[0].price_decision == pytest.approx(500.0)
    assert measured[0].price_fill == pytest.approx(505.0)
    assert measured[0].slippage == pytest.approx(0.01)
    assert client.submitted == [("SPY", 1.0, "buy"), ("QQQ", 1.0, "buy")]
    # persiste en el recorder (reabriendo el archivo, no solo la conexión viva)
    rows = ExecutionCostRecorder(str(db)).records()
    assert len(rows) == 2


def test_measure_slippage_respeta_qty_y_side(tmp_path):
    db = tmp_path / "costs.db"
    client = FakeMeasurementClient(PRICES, fill_mult=1.0)
    r = ExecutionCostRecorder(str(db))
    try:
        measured = measure_slippage(client, r, ["AAPL"], qty=3, side="sell")
    finally:
        r.close()
    assert measured[0].size == 3.0
    assert client.submitted == [("AAPL", 3, "sell")]


# --------------------------------------------------------------------------- #
# summarize — contrato de salida.
# --------------------------------------------------------------------------- #
def test_summarize_contrato_de_salida():
    # 2 órdenes con |slippage| = 0.01 y comisión 0 → cost=0.01, p50=p95=0.01
    recs = [
        {"date": "2026-08-15", "symbol": "SPY", "slippage": 0.01, "commission_frac": 0.0},
        {"date": "2026-08-15", "symbol": "QQQ", "slippage": 0.01, "commission_frac": 0.0},
    ]
    out = summarize(recs)
    # el contrato de ORDENES_MODULOS.md M4, con las claves exactas
    assert set(out) == {
        "cost_per_side_medido", "n_ordenes", "slippage_p50",
        "slippage_p95", "comision_media", "ventana",
    }
    assert out["n_ordenes"] == 2
    assert out["slippage_p50"] == pytest.approx(0.01)
    assert out["slippage_p95"] == pytest.approx(0.01)
    assert out["comision_media"] == pytest.approx(0.0)
    assert out["cost_per_side_medido"] == pytest.approx(0.01)
    assert out["ventana"] == "2026-08-15 a 2026-08-15"


def test_summarize_usa_p50_p95_numericos_segun_contrato():
    recs = [
        {"date": "d1", "symbol": s, "slippage": slip, "commission_frac": 0.0}
        for s, slip in zip(["A", "B", "C", "D", "E"], [0.01, 0.01, 0.02, 0.02, 0.06])
    ]
    out = summarize(recs)
    abs_slip = np.array([0.01, 0.01, 0.02, 0.02, 0.06])
    assert out["slippage_p50"] == pytest.approx(np.median(abs_slip))
    assert out["slippage_p95"] == pytest.approx(np.percentile(abs_slip, 95))


def test_summarize_vacio_es_error_ruidoso():
    with pytest.raises(ValueError, match="No hay mediciones"):
        summarize([])


# --------------------------------------------------------------------------- #
# AlpacaPaperClient — cliente real, con sesión fake (sin red).
# --------------------------------------------------------------------------- #
def test_cliente_exige_credenciales(monkeypatch):
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        AlpacaPaperClient(base_url=BASE_URL)


def test_cliente_usa_env_vars(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "env-key")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "env-secret")
    c = AlpacaPaperClient(base_url=BASE_URL)
    assert c.api_key == "env-key"
    assert c.secret_key == "env-secret"


def test_cliente_last_trade_price_parsea():
    sess = _FakeSession({"SPY": 500.0})
    c = AlpacaPaperClient(api_key="k", secret_key="s", base_url=BASE_URL, session=sess)
    assert c.last_trade_price("SPY") == pytest.approx(500.0)
    assert sess.get_calls[-1].endswith("/v2/stocks/SPY/trades/latest")
    # el dato vive en el host de DATOS (el bug de 2026-08-18 fue pedirlo al de trading)
    assert sess.get_calls[-1].startswith("https://data.alpaca.markets")
    # headers de autenticación puestos en la sesión
    assert sess.headers.get("APCA-API-KEY-ID") == "k"
    assert sess.headers.get("APCA-API-SECRET-KEY") == "s"


def test_cliente_submit_market_order_posteaa_y_lee_fill():
    sess = _FakeSession(PRICES, fill_mult=1.002)
    c = AlpacaPaperClient(api_key="k", secret_key="s", base_url=BASE_URL, session=sess)
    order = c.submit_market_order("QQQ", 2, "buy")
    url, payload = sess.post_calls[-1]
    assert url.endswith("/v2/orders")
    assert payload["symbol"] == "QQQ"
    assert payload["qty"] == "2"
    assert payload["type"] == "market"
    assert payload["side"] == "buy"
    assert order["filled_avg_price"] == pytest.approx(400 * 1.002)


def test_cliente_falla_si_no_hay_fill():
    sess = _FakeSession(PRICES, filled=False)  # la orden nace rejected
    c = AlpacaPaperClient(api_key="k", secret_key="s", base_url=BASE_URL, session=sess)
    with pytest.raises(RuntimeError, match="sin fill"):
        c.submit_market_order("SPY", 1, "buy")


def test_cliente_espera_el_fill_pendiente_del_paper():
    # El paper real responde pending_new al POST y el fill llega por polling
    # (verificado en vivo 2026-08-18 contra SPY). Se espera, no se registra vacío.
    sess = _FakeSession({"QQQ": 400.0}, fill_mult=1.002, pending_polls=2)
    c = AlpacaPaperClient(api_key="k", secret_key="s", base_url=BASE_URL, session=sess)
    order = c.submit_market_order("QQQ", 1, "buy")
    assert order["status"] == "filled"
    assert order["filled_avg_price"] == pytest.approx(400 * 1.002)
    order_polls = [u for u in sess.get_calls if "/v2/orders/" in u]
    assert len(order_polls) >= 1


def test_cliente_base_url_es_paper_siempre():
    # el default apunta a paper; aunque se pase vacío, nunca a api live
    c = AlpacaPaperClient(api_key="k", secret_key="s")
    assert c.base_url == "https://paper-api.alpaca.markets"
    assert c.base_url.startswith("https://paper-api.alpaca.markets")
    assert c.base_url != "https://api.alpaca.markets"
    # y el dato de mercado va al host de datos de solo lectura
    assert c.market_data_base_url == "https://data.alpaca.markets"


# --------------------------------------------------------------------------- #
# Recorder — persistencia.
# --------------------------------------------------------------------------- #
def test_recorder_roundtrip_preserva_datos(tmp_path):
    db = tmp_path / "costs.db"
    r = ExecutionCostRecorder(str(db))
    try:
        _id = r.record(
            symbol="SPY", side="buy", date="2026-08-15",
            price_decision=500.0, price_fill=501.0, commission_frac=0.0001, size=1.0,
        )
        assert isinstance(_id, int) and _id >= 1
        rows = r.records()
        assert len(rows) == 1
        assert rows[0]["symbol"] == "SPY"
        assert rows[0]["price_decision"] == 500.0
        assert rows[0]["price_fill"] == 501.0
        # slippage = (501-500)/500 = 0.002, firmado
        assert rows[0]["slippage"] == pytest.approx(0.002)
    finally:
        r.close()


def test_recorder_acumula_ordenes(tmp_path):
    db = tmp_path / "costs.db"
    r = ExecutionCostRecorder(str(db))
    try:
        for s in ["SPY", "QQQ"]:
            r.record(symbol=s, side="buy", date="2026-08-15",
                     price_decision=100.0, price_fill=100.0, commission_frac=0.0, size=1.0)
        assert len(r.records()) == 2
    finally:
        r.close()
