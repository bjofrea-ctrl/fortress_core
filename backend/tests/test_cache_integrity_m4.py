"""M4: blindar repair_full_redownload contra descargas frescas corruptas.

Replica la semilla de la re-auditoría externa: un cache BUENO en disco + una
descarga fresca corrupta (retorno hard >20% en large-cap) NO deben pisar el
cache; el cache bueno sobrevive y se registra la razón. También cubre el
camino feliz (fresco válido -> sobreescribe) y el vacío (None -> no toca).
"""
import os

import pandas as pd
import pytest
from app.core.cache_integrity import (
    HARD_THRESHOLD_LARGE_CAP,
    find_intermediate_gaps,
    nyse_trading_days,
    repair_full_redownload,
    validate_returns,
)


def _ohlcv(dates, base=100.0, drift=1.0, volume=1_000_000):
    """Serie OHLCV sintética suave (columnas minúsculas, como _norm)."""
    n = len(dates)
    close = [base + drift * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": [c * 0.999 for c in close],
            "high": [c * 1.01 for c in close],
            "low": [c * 0.99 for c in close],
            "close": close,
            "volume": [volume] * n,
        },
        index=pd.DatetimeIndex(dates),
    )


def _market_days(start, end):
    s_date = pd.Timestamp(start).date()
    e_date = pd.Timestamp(end).date()
    out = []
    y = s_date.year
    while y <= e_date.year:
        for d in nyse_trading_days(y):
            if s_date <= d <= e_date:
                out.append(pd.Timestamp(d))
        y += 1
    return pd.DatetimeIndex(out)


class _FakeDownloader:
    """downloader(ticker, start=..., end=...) -> df fresco (o None/empty)."""

    def __init__(self, fresh):
        self.fresh = fresh

    def __call__(self, ticker, start=None, end=None):
        return self.fresh


def _corrupt(dates):
    """Fresco con un retorno hard (+200%) en un día interior -> basura."""
    df = _ohlcv(dates)
    idx = df.index[10]
    c = df.loc[idx, "close"] * 3.0
    df.loc[idx, "close"] = c
    df.loc[idx, "open"] = c * 0.999
    df.loc[idx, "high"] = c * 1.01
    df.loc[idx, "low"] = c * 0.99
    return df


def test_repair_full_redownload_preserves_good_cache_on_corrupt_fresh(tmp_path, capsys):
    symbol = "AAPL"
    cache_path = str(tmp_path / f"{symbol}.parquet")
    days = _market_days(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-03-29"))
    good = _ohlcv(days)
    good.to_parquet(cache_path)  # cache BUENO en disco

    corrupt = _corrupt(days)
    # sanity: el fresco efectivamente levanta hard-flag
    assert any(f["level"] == "hard" for f in validate_returns(corrupt, symbol))

    repaired = repair_full_redownload(
        symbol, cache_path, _FakeDownloader(corrupt), "2024-01-01", "2024-04-01"
    )

    # el cache en disco NO cambió: sigue siendo el BUENO
    on_disk = pd.read_parquet(cache_path)
    pd.testing.assert_frame_equal(on_disk, good, check_index_type=False, check_column_type=False)

    # la función devuelve el cache conservado (no el fresco corrupto)
    pd.testing.assert_frame_equal(repaired, good, check_index_type=False, check_column_type=False)

    # se registró la razón
    out = capsys.readouterr().out
    assert "cache existente conservado" in out
    assert "descarga fresca inválida" in out
    assert "retorno anómalo hard" in out


def test_repair_full_redownload_overwrites_on_valid_fresh(tmp_path):
    symbol = "AAPL"
    cache_path = str(tmp_path / f"{symbol}.parquet")
    days = _market_days(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-03-29"))
    good = _ohlcv(days)
    good.to_parquet(cache_path)

    fresh = _ohlcv(days)  # fresco válido: sin hard flags, sin huecos
    assert validate_returns(fresh, symbol) == []
    assert find_intermediate_gaps(fresh) == []

    repaired = repair_full_redownload(
        symbol, cache_path, _FakeDownloader(fresh), "2024-01-01", "2024-04-01"
    )

    # el disco ahora tiene el fresco (sobrescrito)
    on_disk = pd.read_parquet(cache_path)
    pd.testing.assert_frame_equal(on_disk, fresh, check_index_type=False, check_column_type=False)
    pd.testing.assert_frame_equal(repaired, fresh, check_index_type=False, check_column_type=False)


def test_repair_full_redownload_empty_fresh_leaves_cache_untouched(tmp_path):
    symbol = "AAPL"
    cache_path = str(tmp_path / f"{symbol}.parquet")
    days = _market_days(pd.Timestamp("2024-01-02"), pd.Timestamp("2024-03-29"))
    good = _ohlcv(days)
    good.to_parquet(cache_path)

    repaired = repair_full_redownload(
        symbol, cache_path, _FakeDownloader(None), "2024-01-01", "2024-04-01"
    )
    assert repaired is None
    on_disk = pd.read_parquet(cache_path)
    pd.testing.assert_frame_equal(on_disk, good, check_index_type=False, check_column_type=False)
