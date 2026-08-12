"""Tests de integración del router /api/market/live (yfinance).

yf se monkeypatchea por completo: nunca hay red. Se cubren el contrato de
overview (incluido el cache de 30s) y de /{symbol} (info + intraday + error).
"""
import asyncio
import os

import pandas as pd
import pytest
from app.api.routes import live
from fastapi import HTTPException


class _FakeFastInfo:
    def __init__(self, price=100.0, prev=95.0, cap=10**9):
        self._data = {"last_price": price, "previous_close": prev, "market_cap": cap}

    def get(self, key, default=0):
        return self._data.get(key, default)


class _FakeTicker:
    def __init__(self, symbol, info=None):
        self.symbol = symbol
        self.info = info or {
            "regularMarketPrice": 100.0,
            "regularMarketChange": 1.2,
            "regularMarketChangePercent": 1.2,
            "regularMarketPreviousClose": 98.8,
            "regularMarketOpen": 99.0,
            "regularMarketDayHigh": 101.0,
            "regularMarketDayLow": 98.5,
            "regularMarketVolume": 1000000,
            "marketCap": 10**9,
            "fiftyTwoWeekHigh": 120.0,
            "fiftyTwoWeekLow": 80.0,
            "trailingPE": 15.3,
            "trailingEps": 6.5,
            "dividendYield": 0.012,
            "beta": 1.05,
            "sector": "Technology",
            "industry": "Semiconductors",
            "currency": "USD",
            "exchange": "NASDAQ",
            "shortName": "TESTA",
            "longName": "Test Alpha Inc.",
        }
        self.fast_info = _FakeFastInfo()


def _patch_yf(monkeypatch, ticker=None, intraday=None):
    class _YFFake:
        def Ticker(self, symbol):
            if ticker is not None:
                return ticker(symbol)
            return _FakeTicker(symbol)

        def download(self, *args, **kwargs):
            return intraday if intraday is not None else pd.DataFrame()

    monkeypatch.setattr(live, "yf", _YFFake())


def test_overview_sin_cache_dir(monkeypatch, tmp_path):
    _patch_yf(monkeypatch)
    real_exists = os.path.exists
    monkeypatch.setattr(
        live.os.path, "exists",
        lambda p: False if p == "data/cache" else real_exists(p),
    )
    body = asyncio.run(live.get_live_overview())
    assert body["symbols"] == []
    assert body["timestamp"] is None


def test_overview_construye_y_cachea(monkeypatch):
    _patch_yf(monkeypatch, ticker=lambda s: _FakeTicker(s))
    monkeypatch.setattr(live.os, "listdir",
                        lambda p: ["TESTA.parquet"] if p == "data/cache" else live.os.listdir(p))

    body1 = asyncio.run(live.get_live_overview())
    assert len(body1["symbols"]) == 1
    s = body1["symbols"][0]
    assert s["symbol"] == "TESTA" and s["price"] == 100.0 and s["change_pct"] == round(5.0 / 95.0 * 100, 2)

    body2 = asyncio.run(live.get_live_overview())
    assert body2["timestamp"] == body1["timestamp"], "segunda llamada sale del cache"


def test_live_symbol_estructura_completa(monkeypatch):
    intraday = pd.DataFrame(
        {"Close": [100.0, 100.5], "Volume": [1000, 1100]},
        index=pd.date_range("2024-01-02 09:30", periods=2, freq="5min"),
    )
    _patch_yf(monkeypatch, ticker=lambda s: _FakeTicker(s), intraday=intraday)

    body = asyncio.run(live.get_live_symbol("TESTA"))
    assert body["symbol"] == "TESTA"
    assert body["price"] == 100.0
    assert body["pe_ratio"] == 15.3
    assert body["sector"] == "Technology"
    assert len(body["intraday"]) == 2
    assert set(body["intraday"][0].keys()) == {"datetime", "close", "volume"}


def test_live_symbol_error_es_500(monkeypatch):
    def failing(symbol):
        raise ValueError("sin red")

    _patch_yf(monkeypatch, ticker=failing)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(live.get_live_symbol("ERROR_SYM"))
    assert exc.value.status_code == 500
