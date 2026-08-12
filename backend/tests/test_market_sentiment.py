"""Tests del cache TTL semanal de AAII y del degradado a baseline.

Guardas pedidas por revisión (2026-08-10) ANTES de conectar el data feeding:
1. fetch_aaii() en el request en vivo lee el parquet (TTL semanal) — nunca
   descarga el xls por request.
2. Si la descarga falla, degrada al cache stale; solo sin cache propaga el
   error (y _load_sentiment_data en predict.py lo captura -> baseline).
"""
import os
import time

import pandas as pd
import pytest
from app.core import market_sentiment
from app.core.market_sentiment import AAII_CACHE_MAX_AGE_DAYS, fetch_aaii


def _fake_xls_df(n_weeks: int = 500) -> pd.DataFrame:
    """Mini-xls AAII sintético: headers en fila 3, datos desde fila 5,
    fila de resumen final 'Count YY' que hay que descartar."""
    rows = [[None] * 8 for _ in range(5)]
    rows[3] = ["Date", "Bullish", "Neutral", "Bearish", "Total", "Mov Avg", "Spread", "Average"]
    start = pd.Timestamp("2015-01-01")
    for i in range(n_weeks):
        d = start + pd.Timedelta(weeks=i)
        rows.append([d, 0.40, 0.30, 0.30, None, None, None, None])
    rows.append(["Count 2026", None, None, None, None, None, None, None])
    return pd.DataFrame(rows)


@pytest.fixture
def fake_remote(monkeypatch):
    """Mockea la descarga: _get responde 200 con bytes basura y
    pd.read_excel devuelve el xls sintético."""
    class _Resp:
        status_code = 200
        content = b"fake-xls"

        def raise_for_status(self):
            pass

    calls = {"count": 0}

    def fake_get(url, timeout=60):
        calls["count"] += 1
        return _Resp()

    monkeypatch.setattr(market_sentiment, "_get", fake_get)
    monkeypatch.setattr(pd, "read_excel", lambda buf, header=None: _fake_xls_df())
    return calls


@pytest.fixture
def fresh_cache(tmp_path, monkeypatch):
    """Cache parquet reciente (mtime de hoy) en directorio aislado."""
    monkeypatch.setattr(market_sentiment, "CACHE_DIR", str(tmp_path))
    out = pd.Series([-10.0, 12.0], index=pd.DatetimeIndex(["2026-07-30", "2026-08-06"]))
    out.to_frame("value").to_parquet(market_sentiment._aaii_cache_path())
    return market_sentiment._aaii_cache_path()


def _age_days(path: str, days: float) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_cache_fresh_does_not_download(fresh_cache, fake_remote):
    """Cache reciente -> se lee el parquet, el xls NO se descarga."""
    got = fetch_aaii()
    assert list(got.index) == list(pd.DatetimeIndex(["2026-07-30", "2026-08-06"]))
    assert fake_remote["count"] == 0


def test_stale_cache_refreshes_when_download_ok(fresh_cache, fake_remote):
    """Cache viejo -> se re-descarga y el parquet se actualiza."""
    _age_days(fresh_cache, AAII_CACHE_MAX_AGE_DAYS + 10)
    got = fetch_aaii()
    assert fake_remote["count"] == 1
    assert len(got) >= 400  # xls nuevo completo
    assert (os.path.getmtime(fresh_cache)) > time.time() - 3600


def test_stale_cache_degrades_to_stale_on_failure(fresh_cache, monkeypatch):
    """Cache viejo + descarga falla -> devuelve el stale (no propaga)."""
    _age_days(fresh_cache, AAII_CACHE_MAX_AGE_DAYS + 10)

    def failing_get(url, timeout=60):
        raise RuntimeError("network down")

    monkeypatch.setattr(market_sentiment, "_get", failing_get)
    got = fetch_aaii()
    assert list(got.index) == list(pd.DatetimeIndex(["2026-07-30", "2026-08-06"]))


def test_no_cache_download_failure_propagates(tmp_path, monkeypatch):
    """Sin cache + descarga falla -> propaga (el caller degrada a baseline)."""
    monkeypatch.setattr(market_sentiment, "CACHE_DIR", str(tmp_path))

    def failing_get(url, timeout=60):
        raise RuntimeError("network down")

    monkeypatch.setattr(market_sentiment, "_get", failing_get)
    with pytest.raises(RuntimeError):
        fetch_aaii()


def test_no_cache_download_ok_creates_parquet(tmp_path, monkeypatch):
    """Sin cache + descarga ok -> crea el parquet."""
    monkeypatch.setattr(market_sentiment, "CACHE_DIR", str(tmp_path))

    class _Resp:
        status_code = 200
        content = b"fake-xls"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(market_sentiment, "_get", lambda url, timeout=60: _Resp())
    monkeypatch.setattr(pd, "read_excel", lambda buf, header=None: _fake_xls_df())
    got = fetch_aaii()
    assert len(got) >= 400
    assert os.path.exists(market_sentiment._aaii_cache_path())


def test_bad_format_does_not_overwrite_good_cache(fresh_cache, monkeypatch):
    """xls con formato inesperado (pocas filas) -> no pisa el cache bueno."""
    _age_days(fresh_cache, AAII_CACHE_MAX_AGE_DAYS + 10)
    monkeypatch.setattr(pd, "read_excel", lambda buf, header=None: _fake_xls_df(n_weeks=3))
    got = fetch_aaii()
    assert list(got.index) == list(pd.DatetimeIndex(["2026-07-30", "2026-08-06"]))
