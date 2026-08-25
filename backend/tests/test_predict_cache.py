"""Tests del cache TTL de /api/predict (H2.3, 2026-08-25).

Patrón advisor.py::_get_context: cache en memoria + asyncio.Lock + threadpool.
Se verifica el COMPORTAMIENTO del cache (no la mecánica interna):
- 2º request dentro del TTL NO re-descarga (el bug H2.3: ~57 descargas/request);
- TTL expirado -> re-carga;
- símbolo fuera del universo canónico -> fallback a descarga directa;
- analyze_universe sirve todo el universo desde UNA sola carga.
"""
import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from app.api.routes import predict
from app.core.predictive_engine import PredictiveEngine


def _df(n=250, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    return pd.DataFrame({"close": close},
                        index=pd.bdate_range("2023-01-02", periods=n))


def _fake_result(symbol="TESTA"):
    return SimpleNamespace(
        symbol=symbol, timestamp="2024-01-02T00:00:00",
        regime_state=0, regime_name="GOLDILOCKS",
        technical_score=0.3, fundamental_score=0.1, macro_score=0.2,
        sentiment_score=0.0, volatility_score=0.1, composite_score=0.55,
        decision="COMPRAR", confidence=0.7,
        prob_up_short=0.6, prob_up_medium=0.55, prob_up_long=0.52,
        manipulation_risk=0.05, manipulation_signals=[],
        triad_score=0.4, triad_recommendation="COMPRAR", triad_agreement="ALTO",
        triad_consensus=SimpleNamespace(bull_score=0.5, bear_score=-0.2,
                                        contrarian_score=0.1),
        signals=[],
    )


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Cada test arranca con el cache frío y lo deja frío al salir."""
    predict._data_cache = None
    predict._data_cache_time = 0.0
    yield
    predict._data_cache = None
    predict._data_cache_time = 0.0


def _stub_io(monkeypatch, symbols=("TESTA",), result=None):
    """Stubea I/O externo + motor; devuelve el contador de descargas."""
    calls = {"n": 0}

    def fake_download(symbol, start="2015-01-01"):
        calls["n"] += 1
        return _df(seed=calls["n"])

    monkeypatch.setattr(predict, "SYMBOLS", list(symbols))
    monkeypatch.setattr(predict, "download_data", fake_download)
    monkeypatch.setattr(predict, "_load_macro_data", lambda: {})
    monkeypatch.setattr(predict, "_load_sentiment_data", lambda: None)
    monkeypatch.setattr(predict, "get_fundamentals_api", lambda symbol: None)
    res = result or _fake_result()
    monkeypatch.setattr(PredictiveEngine, "analyze", lambda self, **kw: res)
    return calls


def test_symbol_segundo_request_no_redisca(monkeypatch):
    calls = _stub_io(monkeypatch, symbols=("TESTA",))
    r1 = asyncio.run(predict.analyze_symbol("TESTA"))
    assert calls["n"] == 1  # carga fría: 1 descarga (universo de 1 símbolo)
    r2 = asyncio.run(predict.analyze_symbol("TESTA"))
    assert calls["n"] == 1, "2º request dentro del TTL re-descargó (cache no funciona)"
    assert r1["symbol"] == r2["symbol"] == "TESTA"


def test_universe_dos_requests_una_sola_carga(monkeypatch):
    calls = _stub_io(monkeypatch, symbols=("AAA", "BBB"), result=_fake_result("AAA"))
    b1 = asyncio.run(predict.analyze_universe(regime_state=0))
    assert calls["n"] == 2  # AAA + BBB, una vez cada uno
    b2 = asyncio.run(predict.analyze_universe(regime_state=0))
    assert calls["n"] == 2, "/universe re-descargó el universo en el 2º request"
    assert b1["count"] == 2 and b2["count"] == 2


def test_ttl_expirado_redisca(monkeypatch):
    calls = _stub_io(monkeypatch, symbols=("TESTA",))
    asyncio.run(predict.analyze_symbol("TESTA"))
    assert calls["n"] == 1
    # forzar expiración del TTL sin dormir 5 minutos
    predict._data_cache_time -= predict._DATA_CACHE_TTL_SECONDS + 1
    asyncio.run(predict.analyze_symbol("TESTA"))
    assert calls["n"] == 2, "TTL expirado debería haber re-cargado"


def test_simbolo_fuera_de_universo_fallback_directo(monkeypatch):
    calls = _stub_io(monkeypatch, symbols=(), result=_fake_result("OTRA"))
    body = asyncio.run(predict.analyze_symbol("otra"))
    assert body["symbol"] == "OTRA"
    assert calls["n"] == 1  # solo el fallback directo (universo vacío)


def test_series_cortas_descartadas_en_cache(monkeypatch):
    """El loader del cache aplica el mismo filtro >=200 filas que había por request."""
    def fake_download(symbol, start="2015-01-01"):
        return _df() if symbol != "CORTO" else _df(n=50)

    monkeypatch.setattr(predict, "SYMBOLS", ["CORTO", "LARGO"])
    monkeypatch.setattr(predict, "download_data", fake_download)
    monkeypatch.setattr(predict, "_load_macro_data", lambda: {})
    prices, _ = asyncio.run(predict._get_data())
    assert "LARGO" in prices and "CORTO" not in prices
