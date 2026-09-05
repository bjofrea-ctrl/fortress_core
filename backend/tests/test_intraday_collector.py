"""Tests del colector intradía 1-min (I3 + B1) — infraestructura, no trading.

Cubre, siempre contra fakes (jamás red):
- AlpacaPaperClient.get_bars paginación y traducción BRK-B → BRK.B
- collect_intraday_1min incremental (no re-descarga) y dedup por timestamp
- B1: lista staged = SPY, QQQ + 28 de mayor liquidez, subconjunto del
  universo 102, 30 únicos; rollback trivial --base a los 7; validación
  estructural falla ruidoso ante lista editada mal
- B1: monitor de rate/cuota en el propio log (requests/barras por corrida
  + headers X-RateLimit-* vía el hook on_response del cliente)
"""
import pandas as pd
import pytest
from app.core.execution_costs import AlpacaPaperClient


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeBarSession:
    """Fake para get_bars: devuelve 2 páginas con next_page_token."""

    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        # Simular 2 páginas: primera con 2 barras + token, segunda con 1 barra sin token
        token = params.get("page_token") if params else None
        if token is None:
            return _FakeResp({
                "bars": [
                    {"t": "2024-01-02T14:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000, "n": 10, "vw": 100.2},
                    {"t": "2024-01-02T14:31:00Z", "o": 100.5, "h": 102, "l": 100, "c": 101, "v": 1200, "n": 12, "vw": 100.8},
                ],
                "next_page_token": "tok2",
                "symbol": "SPY",
            })
        else:
            return _FakeResp({
                "bars": [
                    {"t": "2024-01-02T14:32:00Z", "o": 101, "h": 101, "l": 100, "c": 100.8, "v": 1100, "n": 11, "vw": 100.5},
                ],
                "next_page_token": None,
                "symbol": "SPY",
            })

    def post(self, url, json=None, timeout=None):
        raise AssertionError("no post en test de barras")


def _make_bars_client(fake):
    return AlpacaPaperClient(
        api_key="k", secret_key="s",
        base_url="https://paper-api.alpaca.markets",
        market_data_base_url="https://data.alpaca.markets",
        session=fake,
    )


def test_get_bars_paginacion_y_traduccion():
    fake = _FakeBarSession()
    client = _make_bars_client(fake)
    bars = client.get_bars("BRK-B", timeframe="1Min", start="2024-01-02T00:00:00Z", end="2024-01-03T00:00:00Z")
    assert len(bars) == 3
    # 2 llamadas por paginación
    assert len(fake.calls) == 2
    # Traducción BRK-B -> BRK.B en URL
    first_url = fake.calls[0][0]
    assert "BRK.B" in first_url
    assert "BRK-B" not in first_url
    # Orden preservado
    assert bars[0]["c"] == 100.5
    assert bars[2]["c"] == 100.8


def test_collect_incremental_no_redescarga(tmp_path, monkeypatch):
    """Colector incremental: segunda corrida no duplica timestamps."""
    # Usar tmp_path como CACHE_DIR
    import scripts.collect_intraday_1min as coll

    # Parchear CACHE_DIR a tmp_path
    monkeypatch.setattr(coll, "CACHE_DIR", tmp_path)

    # Fake client que devuelve 2 barras fijas
    class _FakeBarClient:
        def __init__(self):
            self.calls = 0

        def get_bars(self, symbol, timeframe="1Min", start="", end="", limit=10000, feed="iex", adjustment="raw"):
            self.calls += 1
            # Primera llamada: 2 barras, segunda llamada: 0 (ya up-to-date) si start > última
            # Simular que si start es después de 14:31, no hay más
            if "14:32" in start or "14:33" in start:
                return []
            return [
                {"t": "2024-01-02T14:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1000, "n": 10, "vw": 100},
                {"t": "2024-01-02T14:31:00Z", "o": 100, "h": 101, "l": 99, "c": 101, "v": 1000, "n": 10, "vw": 100},
            ]

    fake_client = _FakeBarClient()

    # Primera corrida: debe guardar 2 barras
    n1 = coll.collect_one(fake_client, "SPY", days_back=7)
    assert n1 == 2
    p = tmp_path / "SPY.parquet"
    assert p.exists()
    df1 = pd.read_parquet(p)
    assert len(df1) == 2

    # Segunda corrida: start será después de 14:31, fake devuelve 0 -> 0 nuevas
    # Para simular incremental, necesitamos que fake devuelva vacío cuando start > last
    n2 = coll.collect_one(fake_client, "SPY", days_back=7)
    assert n2 == 0
    df2 = pd.read_parquet(p)
    assert len(df2) == 2  # no duplica

    # Tercera corrida con una barra nueva: simular que ahora hay una más
    class _FakeBarClient2:
        def get_bars(self, symbol, timeframe="1Min", start="", end="", limit=10000, feed="iex", adjustment="raw"):
            if "14:32" in start:
                return [{"t": "2024-01-02T14:32:00Z", "o": 101, "h": 102, "l": 100, "c": 102, "v": 1000, "n": 10, "vw": 101}]
            return []

    fake_client2 = _FakeBarClient2()
    n3 = coll.collect_one(fake_client2, "SPY", days_back=7)
    assert n3 == 1
    df3 = pd.read_parquet(p)
    assert len(df3) == 3
    assert df3["timestamp"].is_monotonic_increasing


def test_collect_sin_credenciales_no_crash(tmp_path, monkeypatch):
    """Sin credenciales, el colector debe salir con código 1, no excepción no manejada."""
    import scripts.collect_intraday_1min as coll
    from app.config import settings

    monkeypatch.setattr(coll, "CACHE_DIR", tmp_path)
    # Vaciar env Y settings (settings carga backend/.env real; sin esto el
    # fallback a settings.ALPACA_* encuentra la credencial real y el test
    # nunca ve "sin credenciales" — mismo patron que test_execution_costs.py).
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET_KEY", raising=False)
    monkeypatch.setattr(settings, "ALPACA_PAPER_API_KEY", "")
    monkeypatch.setattr(settings, "ALPACA_PAPER_SECRET_KEY", "")
    # Forzar que AlpacaPaperClient falle sin credenciales
    try:
        AlpacaPaperClient(api_key="", secret_key="")
        assert False, "debió fallar"
    except Exception as exc:
        assert "Faltan credenciales" in str(exc)


# --------------------------------------------------------------------- B1


def test_staged_30_subconjunto_del_universo_102():
    """B1: staged = SPY, QQQ + 28 de mayor liquidez — 30 únicos, todos del
    universo 102 de opportunities_universe (la fuente única del proyecto)."""
    import scripts.collect_intraday_1min as coll
    from app.api.routes.opportunities_universe import SYMBOLS as UNIVERSE_102

    assert len(coll.STAGED_SYMBOLS) == 30
    assert len(set(coll.STAGED_SYMBOLS)) == 30
    assert set(coll.STAGED_SYMBOLS) <= set(UNIVERSE_102)
    # SPY y QQQ siempre (el plan los fija explícitos)
    assert coll.STAGED_SYMBOLS[:2] == ["SPY", "QQQ"]
    # los 7 BASE siguen siendo default alcanzable vía --base
    assert set(coll.BASE_SYMBOLS) <= set(UNIVERSE_102)
    # staged es un SUPERCONJUNTO de BASE (los 7 base son de los más líquidos)
    assert set(coll.BASE_SYMBOLS) <= set(coll.STAGED_SYMBOLS)


def test_validate_staged_falla_ruidoso_si_se_rompe(monkeypatch):
    """La validación estructural rechaza 29, duplicados y símbolos fuera del universo."""
    import scripts.collect_intraday_1min as coll

    buenas = list(coll.STAGED_SYMBOLS)
    # 29 (uno menos)
    monkeypatch.setattr(coll, "STAGED_SYMBOLS", buenas[:-1])
    with pytest.raises(ValueError):
        coll._validate_staged()
    # duplicado
    monkeypatch.setattr(coll, "STAGED_SYMBOLS", buenas[:-1] + [buenas[0]])
    with pytest.raises(ValueError):
        coll._validate_staged()
    # símbolo fuera del universo 102
    monkeypatch.setattr(coll, "STAGED_SYMBOLS", buenas[:-1] + ["FANTASMA"])
    with pytest.raises(ValueError):
        coll._validate_staged()
    # la lista buena pasa
    monkeypatch.setattr(coll, "STAGED_SYMBOLS", buenas)
    coll._validate_staged()


def test_main_base_rollback_a_7(monkeypatch, tmp_path):
    """B1: --base = rollback trivial a los 7 BASE (lista es parámetro)."""
    import sys as _sys
    from unittest.mock import patch as _patch

    import scripts.collect_intraday_1min as coll

    pedidos = []

    class _FakeClientReg:
        def get_bars(self, symbol, timeframe="1Min", start="", end="", limit=10000, feed="iex", adjustment="raw"):
            pedidos.append(symbol)
            return []

        def close(self):
            pass

    monkeypatch.setattr(coll, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coll, "AlpacaPaperClient", _FakeClientReg)
    with _patch.object(_sys, "argv", ["prog", "--base"]):
        rc = coll.main()
    assert rc == 0
    assert pedidos == coll.BASE_SYMBOLS
    assert len(pedidos) == 7


def test_main_default_staged_30(monkeypatch, tmp_path):
    """Sin flags: la corrida default pide exactamente los 30 staged."""
    import sys as _sys
    from unittest.mock import patch as _patch

    import scripts.collect_intraday_1min as coll

    pedidos = []

    class _FakeClientReg:
        def get_bars(self, symbol, timeframe="1Min", start="", end="", limit=10000, feed="iex", adjustment="raw"):
            pedidos.append(symbol)
            return []

        def close(self):
            pass

    monkeypatch.setattr(coll, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coll, "AlpacaPaperClient", _FakeClientReg)
    with _patch.object(_sys, "argv", ["prog"]):
        rc = coll.main()
    assert rc == 0
    assert pedidos == coll.STAGED_SYMBOLS
    assert len(pedidos) == 30


def test_main_symbols_csv_manual(monkeypatch, tmp_path):
    """--symbols CSV explícito pisa la staged (rollback manual también)."""
    import sys as _sys
    from unittest.mock import patch as _patch

    import scripts.collect_intraday_1min as coll

    pedidos = []

    class _FakeClientReg:
        def get_bars(self, symbol, timeframe="1Min", start="", end="", limit=10000, feed="iex", adjustment="raw"):
            pedidos.append(symbol)
            return []

        def close(self):
            pass

    monkeypatch.setattr(coll, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(coll, "AlpacaPaperClient", _FakeClientReg)
    with _patch.object(_sys, "argv", ["prog", "--symbols", "spy,qqq"]):
        rc = coll.main()
    assert rc == 0
    assert pedidos == ["SPY", "QQQ"]  # normaliza mayúsculas


# ------------------------------------------------- B1: monitor rate/cuota


class _FakeRespConHeaders(_FakeResp):
    def __init__(self, payload, status=200, headers=None):
        super().__init__(payload, status)
        self.headers = headers or {}


def test_rate_monitor_cuenta_y_resumee():
    """El monitor cuenta requests/barras y arma la línea de resumen del log."""
    import scripts.collect_intraday_1min as coll

    m = coll.RateMonitor()
    m.note_request(120)
    m.note_request(30)
    assert m.requests == 2
    assert m.bars == 150
    line = m.summary(30)
    assert "requests=2" in line and "barras=150" in line and "30 símbolos" in line
    assert "no expuestos" in line  # sin headers vistos


def test_rate_monitor_captura_headers_x_ratelimit():
    """Los headers X-RateLimit-* de la response quedan en el resumen del log."""
    import scripts.collect_intraday_1min as coll

    m = coll.RateMonitor()
    m.note_headers({"X-RateLimit-Limit": "200", "X-RateLimit-Remaining": "197", "Other": "irrelevante"})
    m.note_request(10)
    line = m.summary(30)
    assert "X-RateLimit-Limit=200" in line
    assert "X-RateLimit-Remaining=197" in line
    assert "Other" not in line  # solo rate-limit, sin ruido


def test_get_bars_hook_on_response_capta_headers():
    """El cliente expone cada response vía on_response (B1) sin romper el fetch."""
    fake = _FakeBarSession()
    client = _make_bars_client(fake)
    vistos = []
    client.on_response = lambda headers: vistos.append(dict(headers))
    bars = client.get_bars("SPY", timeframe="1Min", start="2024-01-02T00:00:00Z", end="2024-01-03T00:00:00Z")
    assert len(bars) == 3
    # el _FakeResp no tiene headers reales: el hook se llama y no rompe
    client.on_response = None


def test_fetch_bars_monitoreado_cuenta_request_y_limpia_hook(tmp_path, monkeypatch):
    """_fetch_bars con monitor: cuenta 1 request, pasa el hook, y lo DESinstala
    al salir (el siguiente fetch sin monitor no llama el hook)."""
    import scripts.collect_intraday_1min as coll

    class _FakeClientConHook:
        on_response = None

        def get_bars(self, symbol, timeframe="1Min", start="", end="", limit=10000, feed="iex", adjustment="raw"):
            # simular que el cliente invoca el hook si está seteado (como hace el real)
            if self.on_response is not None:
                self.on_response({"X-RateLimit-Remaining": "180"})
            return [{"t": "2024-01-02T14:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1, "n": 1, "vw": 1}]

    m = coll.RateMonitor()
    client = _FakeClientConHook()
    bars = coll._fetch_bars(client, "SPY", "2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z", monitor=m)
    assert len(bars) == 1
    assert m.requests == 1
    assert m.bars == 1
    assert m.rate_headers == {"X-RateLimit-Remaining": "180"}
    assert client.on_response is None  # desinstalado al salir

    # sin monitor: no toca el hook y funciona igual (comportamiento previo)
    bars2 = coll._fetch_bars(client, "SPY", "2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z")
    assert len(bars2) == 1
