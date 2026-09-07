"""Tests de M4 — costos medidos (app/core/execution_costs.py).

El test que más importa acá NO es "el código corre" — es que la medición se puede
verificar con un fake del cliente de Alpaca, sin pegar a la red, y que el contrato de
salida sale exactamente como lo especifica ORDENES_MODULOS.md M4. La API se mockea
siempre: jamás una orden real ni en paper desde los tests.
"""
import time
import warnings
from unittest.mock import patch
import numpy as np
import pytest
from app.core.execution_costs import (
    AlpacaPaperClient,
    ConfigurationError,
    ExecutionCostRecorder,
    measure_slippage,
    summarize,
    ALPACA_RATE_LIMIT_PER_MIN,
    RATE_WARN_THRESHOLD,
    RATE_THROTTLE_THRESHOLD,
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

    def request(self, method, url, **kwargs):
        """Interfaz session.request (B1 rate-monitor enruta por acá);
        delega en get/post como la sesión real de requests."""
        if method.upper() == "POST":
            return self.post(url, **kwargs)
        return self.get(url, **kwargs)

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

    def request(self, method: str, url: str, **kwargs):
        """Wrapper compatible con requests.Session.request."""
        if method.upper() == "GET":
            return self.get(url, **kwargs)
        elif method.upper() == "POST":
            return self.post(url, **kwargs)
        else:
            raise NotImplementedError(f"method {method} not implemented in _FakeSession")

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
    from app.config import settings

    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)
    monkeypatch.setattr(settings, "ALPACA_PAPER_API_KEY", "")
    monkeypatch.setattr(settings, "ALPACA_PAPER_SECRET_KEY", "")
    with pytest.raises(ConfigurationError):
        AlpacaPaperClient(base_url=BASE_URL)


def test_cliente_usa_env_vars(monkeypatch):
    from app.config import settings

    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "env-key")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "env-secret")
    # Parchear settings a valores falsos explícitos para no depender del .env real
    monkeypatch.setattr(settings, "ALPACA_PAPER_API_KEY", "fake-test-key")
    monkeypatch.setattr(settings, "ALPACA_PAPER_SECRET_KEY", "fake-test-secret")
    c = AlpacaPaperClient(base_url=BASE_URL)
    # Precedencia: env var runtime > settings/.env
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


def test_cliente_normaliza_simbolos_con_guion():
    # el motor usa BRK-B (formato yahoo); la API de Alpaca exige BRK.B.
    # Sin esta traducción la ronda viva de 2026-08-18 murió con 400 en el dato.
    sess = _FakeSession({"BRK.B": 450.0}, fill_mult=1.001)
    c = AlpacaPaperClient(api_key="k", secret_key="s", base_url=BASE_URL, session=sess)
    assert c.last_trade_price("BRK-B") == pytest.approx(450.0)
    order = c.submit_market_order("BRK-B", 1, "buy")
    _, payload = sess.post_calls[-1]
    assert payload["symbol"] == "BRK.B"
    assert order["filled_avg_price"] == pytest.approx(450.0 * 1.001)


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


# --------------------------------------------------------------------------- #
# AlpacaPaperClient — Rate Limit Monitor (B1)
# --------------------------------------------------------------------------- #
# Límite Alpaca paper: 200 req/min. Warn al 70% (140), throttle al 85% (170).
# Ventana deslizante: 60s. Tests usan monkeypatch time.monotonic + catch_warnings.
# El mock de time.sleep debe TAMBIÉN avanzar time.monotonic para simular paso del tiempo real.

def _make_rate_test_client(monkeypatch, base_time, time_step=0.01, max_calls=200):
    """Helper: crea cliente con time.monotonic y time.sleep mockeados que avanzan el reloj."""
    time_vals = [base_time + i * time_step for i in range(max_calls)]
    call_count = 0
    sleep_advance = 0.0

    def mock_monotonic():
        nonlocal call_count, sleep_advance
        if call_count < len(time_vals):
            t = time_vals[call_count] + sleep_advance
            call_count += 1
            return t
        return time_vals[-1] + sleep_advance

    monkeypatch.setattr(time, "monotonic", mock_monotonic)

    sleep_calls = []

    def mock_sleep(s):
        nonlocal sleep_advance
        sleep_calls.append(s)
        sleep_advance += s  # avanazar reloj simulado

    monkeypatch.setattr(time, "sleep", mock_sleep)

    def make_client(prices):
        sess = _FakeSession(prices, fill_mult=1.0, pending_polls=0)
        return AlpacaPaperClient(api_key="k", secret_key="s", base_url=BASE_URL, session=sess), sleep_calls

    return make_client


def test_rate_monitor_warn_al_70_porciento(monkeypatch):
    """Al llegar a 140 req/min (70%), emite RuntimeWarning visible."""
    make_client = _make_rate_test_client(monkeypatch, base_time=1_000_000.0, max_calls=150)

    prices = {f"SYM{i}": 100.0 + i for i in range(150)}
    c, sleep_calls = make_client(prices)

    # Hacer 139 requests = 69.5% -> sin warn
    for i in range(139):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            c.last_trade_price(f"SYM{i}")
            assert not any("RATE WARN" in str(x.message) for x in w), f"warn prematuro en request {i}"

    # Request 140 = 70% -> WARNING
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c.last_trade_price("SYM140")
        assert any("RATE WARN" in str(x.message) for x in w), "no se emitió warn al 70%"
        assert "140/200 req/min" in str(w[0].message)


def test_rate_monitor_throttle_al_85_porciento(monkeypatch):
    """Al llegar a 170 req/min (85%), aplica sleep escalonado y re-chequea."""
    make_client = _make_rate_test_client(monkeypatch, base_time=2_000_000.0, max_calls=180)

    prices = {f"SYM{i}": 100.0 + i for i in range(180)}
    c, sleep_calls = make_client(prices)

    # Hacer 169 requests = 84.5% -> sin throttle
    for i in range(169):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            c.last_trade_price(f"SYM{i}")
            assert not any("RATE THROTTLE" in str(x.message) for x in w)

    # Request 170 = 85% -> THROTTLE (sleep 0.5s)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c.last_trade_price("SYM170")
        assert any("RATE THROTTLE" in str(x.message) for x in w), "no se emitió throttle al 85%"
        assert "170/200 req/min" in str(w[0].message)
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.5, abs=0.1)


def test_rate_monitor_throttle_escalonado_si_sigue_sobre_limite(monkeypatch):
    """Si tras sleep sigue sobre 85%, sleep escala: 0.5s -> 1.0s -> 2.0s..."""
    make_client = _make_rate_test_client(monkeypatch, base_time=3_000_000.0, max_calls=175)

    prices = {f"SYM{i}": 100.0 + i for i in range(175)}
    c, sleep_calls = make_client(prices)

    # 170 requests -> throttle 0.5s
    for i in range(170):
        c.last_trade_price(f"SYM{i}")

    # request 171: sleep avanza reloj 0.5s, pero ventana sigue teniendo 171 req (61s no pasó)
    # -> segundo throttle 1.0s
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c.last_trade_price("SYM171")
        assert any("RATE THROTTLE" in str(x.message) for x in w)
    # sleep 0.5s (first throttle) + 1.0s (second throttle)
    assert len(sleep_calls) == 2
    assert sleep_calls[0] == pytest.approx(0.5, abs=0.1)
    assert sleep_calls[1] == pytest.approx(1.0, abs=0.1)


def test_rate_monitor_ventana_deslizante_limpia_timestamps_viejos(monkeypatch):
    """Requests > 60s se eliminan de la ventana -> contador baja."""
    make_client = _make_rate_test_client(monkeypatch, base_time=4_000_000.0, max_calls=151)

    # Precios para 151 símbolos (0-150)
    prices = {f"SYM{i}": 100.0 + i for i in range(151)}
    c, sleep_calls = make_client(prices)

    # Hacer 100 requests a t=0
    for i in range(100):
        c.last_trade_price(f"SYM{i}")

    # Mock time.monotonic para saltar 61s
    # El helper usa time_step=0.01, así que necesitamos avanzar manualmente
    # El sleep de 61s será simulado por el helper si lo llamamos, pero aquí no hay sleep.
    # En su lugar, recreamos el cliente con base_time avanzado 61s para los requests 101+
    # Más simple: hacemos 100 req, luego creamos NUEVO cliente con base_time + 61
    # (simula que pasó 1 minuto real)

    # Verificar que ventana tiene 100 requests
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c.last_trade_price("SYM100")
        # 101 req en ventana -> 50.5% -> sin warn
        assert not any("RATE WARN" in str(x.message) for x in w)

    # Ahora simular que pasó 61s: recrear cliente con base_time + 61
    # (en test real, el tiempo real avanza; aquí recreamos)
    make_client2 = _make_rate_test_client(monkeypatch, base_time=4_000_061.0, max_calls=51)
    c2, _ = make_client2(prices)
    # Los timestamps del cliente anterior NO se comparten (nueva instancia)
    # Así que este test verifica la limpieza dentro de UNA instancia:
    # hacemos 100 req, luego 61s de sleep simulado (mock_sleep), luego verificamos

    # Test correcto: un cliente, 100 req, sleep 61s, luego más req
    make_client3 = _make_rate_test_client(monkeypatch, base_time=4_000_000.0, max_calls=151)
    c3, sleep_calls3 = make_client3(prices)
    for i in range(100):
        c3.last_trade_price(f"SYM{i}")

    # Simular sleep de 61s llamando a sleep (que avanza sleep_advance)
    time.sleep(61.0)  # esto avanza el reloj interno del mock

    # Ahora ventana debería tener solo los req hechos después del sleep (0)
    # Hacer 50 req más = 50 req/min -> sin warn
    for i in range(100, 150):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            c3.last_trade_price(f"SYM{i}")
            assert not any("RATE WARN" in str(x.message) for x in w), f"warn en req {i} tras sleep 61s"


def test_rate_monitor_no_emit_warn_si_bajo_70(monkeypatch):
    """Confirmar que NO hay warn si siempre bajo 140 req/min."""
    make_client = _make_rate_test_client(monkeypatch, base_time=5_000_000.0, time_step=0.5, max_calls=100)

    prices = {f"SYM{i}": 100.0 + i for i in range(100)}
    c, sleep_calls = make_client(prices)

    for i in range(100):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            c.last_trade_price(f"SYM{i}")
            assert not any("RATE WARN" in str(x.message) for x in w)


def test_rate_monitor_throttle_cap_5s(monkeypatch):
    """Sleep máximo 5s aunque exceda mucho el límite."""
    make_client = _make_rate_test_client(monkeypatch, base_time=6_000_000.0, max_calls=250)

    prices = {f"SYM{i}": 100.0 + i for i in range(250)}
    c, sleep_calls = make_client(prices)

    # Llenar hasta 250 req/min (25% sobre límite) -> throttle múltiple
    for i in range(250):
        c.last_trade_price(f"SYM{i}")

    # Verificar que ningún sleep supera 5s
    assert all(s <= 5.0 for s in sleep_calls), f"sleep supera cap 5s: {sleep_calls}"


def test_rate_monitor_usa_stacklevel_correcto(monkeypatch):
    """stacklevel=4 para que el warning apunte al caller del cliente, no interno."""
    make_client = _make_rate_test_client(monkeypatch, base_time=7_000_000.0, max_calls=150)

    prices = {f"SYM{i}": 100.0 + i for i in range(150)}
    c, sleep_calls = make_client(prices)

    # Llegar al 70%
    for i in range(140):
        c.last_trade_price(f"SYM{i}")

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        c.last_trade_price("SYM140")
        # El filename en el warning debe ser ESTE archivo de test, no execution_costs.py
        assert len(w) == 1
        # stacklevel=4 apunta al llamador de _rate_limit_check -> _request -> last_trade_price -> TEST
        assert "test_execution_costs.py" in w[0].filename
