"""Tests de integración del router /api/market.

download_data se monkeypatchea (nunca red); CACHE_DIR se apunta a tmp_path.
Los indicadores se calculan de verdad (calculate_all_indicators real) sobre
la serie sintética de conftest (400 días, suficiente para ema200).
"""
import asyncio

import pandas as pd
import pytest
from app.api.routes import market

REQUIRED_PRICE_KEYS = ["date", "open", "high", "low", "close", "volume"]
REQUIRED_INDICATOR_KEYS = ["date", "close", "ema20", "ema50", "ema200", "rsi14",
                           "adx14", "atr14", "macd", "macd_signal", "volume_ratio",
                           "momentum_12_1", "volume"]


@pytest.fixture
def cache_dir(tmp_path):
    """CACHE_DIR con 2 parquets sintéticos, con monkeypatch ya aplicado."""
    df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    (tmp_path / "TESTA.parquet").write_bytes(df.to_parquet())
    (tmp_path / "TESTB.parquet").write_bytes(df.to_parquet())
    return str(tmp_path)


def _patch_io(monkeypatch, cache_dir, ohlcv_df):
    monkeypatch.setattr(market, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(market, "download_data",
                        lambda symbol, start="2015-01-01": ohlcv_df)


def test_symbols_lista_cache(monkeypatch, cache_dir, ohlcv_df):
    _patch_io(monkeypatch, cache_dir, ohlcv_df)
    body = asyncio.run(market.get_symbols())
    assert body == {"symbols": ["TESTA", "TESTB"]}


def test_symbols_sin_cache_devuelve_vacio(monkeypatch, tmp_path, ohlcv_df):
    _patch_io(monkeypatch, str(tmp_path / "vacio"), ohlcv_df)
    assert asyncio.run(market.get_symbols()) == {"symbols": []}


def test_prices_respeta_limit(monkeypatch, cache_dir, ohlcv_df):
    _patch_io(monkeypatch, cache_dir, ohlcv_df)
    body = asyncio.run(market.get_prices("TESTA", limit=100))
    assert body["symbol"] == "TESTA"
    assert len(body["data"]) == 100
    assert set(body["data"][0].keys()) == set(REQUIRED_PRICE_KEYS)


def test_indicators_estructura(monkeypatch, cache_dir, ohlcv_df):
    _patch_io(monkeypatch, cache_dir, ohlcv_df)
    body = asyncio.run(market.get_indicators("TESTA", limit=50))
    assert len(body["data"]) == 50

    # los indicadores pesados (ema200) no deben venir None con 400 días
    last = body["data"][-1]
    assert set(last.keys()) == set(REQUIRED_INDICATOR_KEYS) | {
        "bb_upper", "bb_middle", "bb_lower", "stoch_k", "stoch_d"}
    assert last["ema200"] is not None


def test_summary_kpis(monkeypatch, cache_dir, ohlcv_df):
    _patch_io(monkeypatch, cache_dir, ohlcv_df)
    body = asyncio.run(market.get_symbol_summary("TESTA"))
    for key in ["symbol", "last_price", "total_return_pct", "annual_return_pct",
                "annual_volatility_pct", "sharpe_like", "max_drawdown_pct",
                "high_52w", "low_52w", "avg_volume", "date_range", "total_days"]:
        assert key in body, f"falta {key}"
    # calculate_all_indicators descarta el warmup (ema200 ~200d), así que
    # total_days es menor que los 400 del input, pero nunca vacío
    assert 0 < body["total_days"] <= len(ohlcv_df)


def test_overview_ordena_por_return_y_skipea_series_cortas(monkeypatch, cache_dir, ohlcv_df):
    # TESTC existe en cache pero download_data le devuelve pocos días -> se saltea
    monkeypatch.setattr(market, "CACHE_DIR", cache_dir)

    def fake_download(symbol, start="2015-01-01"):
        if symbol == "TESTC":
            return ohlcv_df.iloc[:50]
        return ohlcv_df

    monkeypatch.setattr(market, "download_data", fake_download)
    (pd.DataFrame({"close": [1.0]})).to_parquet(cache_dir + "/TESTC.parquet")

    body = asyncio.run(market.get_market_overview())
    assert len(body["symbols"]) == 2
    returns = [s["total_return_pct"] for s in body["symbols"]]
    assert returns == sorted(returns, reverse=True)
    assert set(body["symbols"][0].keys()) >= {
        "symbol", "price", "total_return_pct", "return_30d_pct", "return_90d_pct",
        "volatility_pct", "high_52w", "low_52w", "range_position", "volume"}
