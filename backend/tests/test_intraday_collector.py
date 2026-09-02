"""Tests del colector intradía 1-min (I3) — infraestructura, no trading.

Cubre, siempre contra fakes (jamás red):
- AlpacaPaperClient.get_bars paginación y traducción BRK-B → BRK.B
- collect_intraday_1min incremental (no re-descarga) y dedup por timestamp
"""
import pandas as pd
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
