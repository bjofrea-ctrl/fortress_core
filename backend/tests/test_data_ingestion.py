"""Tests for backend/app/core/data_ingestion.py::download_data.

Regresion del bug >7: el updater diario (launchd nightly) nunca refrescaba
hasta que el gap superara una semana. Cache quedaba 0-8 dias stale y los dos
estados "no intente" vs "intente pero weekend vacio" eran indistinguibles.

Estos tests habrian atrapado el bug:
- con gap=2 el viejo >7 NO llamaba yf.download; el fix >=1 SI debe llamar.
- con gap=0 no debe llamar; gap=1 si debe (weekend empty se loguea distinto).
- backfill simetrico.
- rama "attempted but empty / no new rows after dedup" loguea señal explicita
  distinta de "no refresh needed".
"""

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _disable_integrity_hook(monkeypatch):
    """Estos tests ejercitan el refresh/backfill con datos sintéticos cuyo
    close salta de 100 a 200 (irreal a propósito): el hook A0 de integridad
    (que vive en download_data) lo flaguearía como salto imposible y entraría
    a re-descargar. El harness tiene sus propios tests en
    test_cache_integrity.py — acá se aísla para probar solo el refresh."""
    import app.core.data_ingestion as di

    monkeypatch.setattr(di, "INTEGRITY_CHECK_ON_UPDATE", False)


def _ohlcv_frame(dates, start_close=100.0):
    n = len(dates)
    close = [start_close + i for i in range(n)]
    return pd.DataFrame(
        {
            "Open": [c * 1.0 for c in close],
            "High": [c * 1.01 for c in close],
            "Low": [c * 0.99 for c in close],
            "Close": close,
            "Volume": [1_000_000] * n,
        },
        index=pd.DatetimeIndex(dates),
    )


def _patch_cache(monkeypatch, tmp_path):
    """Point CACHE_DIR to tmp_path and return the module for patching yf."""
    import app.core.data_ingestion as di

    monkeypatch.setattr(di, "CACHE_DIR", str(tmp_path))
    return di


# ------------------------------------------------------------------ refresh


def test_refresh_gap_2_triggers_download_would_have_been_skipped_with_old_gt7(monkeypatch, tmp_path, capsys):
    """gap=2 debe disparar yf.download (con >7 se saltaba: el bug)."""
    di = _patch_cache(monkeypatch, tmp_path)
    # cache ends 2026-08-20, request end 2026-08-22 => gap 2
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    new_dates = pd.DatetimeIndex([pd.Timestamp("2026-08-21"), pd.Timestamp("2026-08-22")])
    df_new = _ohlcv_frame(new_dates, start_close=200.0)

    calls = {}

    def fake_download(ticker, start=None, end=None, progress=False):
        calls["called"] = True
        calls["start"] = start
        calls["end"] = end
        return df_new

    monkeypatch.setattr(di.yf, "download", fake_download)

    result = di.download_data("AAPL", start="2026-08-10", end="2026-08-22")

    assert calls.get("called") is True, "yf.download should have been called for gap=2 (old >7 would skip)"
    # start of refresh should be last_date of cache
    assert calls["start"] == "2026-08-20"
    # result must include new rows (deduped) and be lowercased
    assert len(result) == len(cache_dates) + len(new_dates)
    assert all(c.islower() for c in result.columns)
    out = capsys.readouterr().out
    assert "[data_ingestion] AAPL refresh: gap 2d" in out
    assert "attempting download" in out
    assert "refreshed 2 rows" in out


def test_refresh_gap_1_triggers_download(monkeypatch, tmp_path, capsys):
    """gap=1 (un dia calendario) debe intentar descarga: daily updater invariant."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    new_dates = pd.DatetimeIndex([pd.Timestamp("2026-08-21")])
    df_new = _ohlcv_frame(new_dates, start_close=200.0)

    calls = {"n": 0}

    def fake_download(ticker, start=None, end=None, progress=False):
        calls["n"] += 1
        return df_new

    monkeypatch.setattr(di.yf, "download", fake_download)

    di.download_data("AAPL", start="2026-08-10", end="2026-08-21")
    assert calls["n"] == 1
    out = capsys.readouterr().out
    assert "gap 1d" in out
    assert "refreshed 1 rows" in out


def test_refresh_gap_0_no_call(monkeypatch, tmp_path, capsys):
    """gap=0 => no refresh needed, no yf call, distinct log."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    def boom(*a, **kw):
        raise AssertionError("yf.download should NOT be called for gap=0")

    monkeypatch.setattr(di.yf, "download", boom)

    # end == last_date => gap 0
    result = di.download_data("AAPL", start="2026-08-10", end="2026-08-20")
    assert len(result) == len(cache_dates)
    out = capsys.readouterr().out
    assert "no refresh needed" in out
    assert "gap 0d" in out
    # ensure we didn't attempt
    assert "attempting download" not in out or "refresh: gap 0" in out


def test_refresh_attempted_but_empty_logs_distinct_signal(monkeypatch, tmp_path, capsys):
    """gap>=1 pero yfinance vacio (weekend) => log 'attempted but ... empty' distinto de 'no refresh needed'."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    monkeypatch.setattr(di.yf, "download", lambda *a, **kw: pd.DataFrame())

    # need gap>=1: request 2026-08-22 (2d), but 2026-08-23 is Sat, so empty is realistic
    result = di.download_data("AAPL", start="2026-08-10", end="2026-08-22")
    assert len(result) == len(cache_dates)  # no new rows
    out = capsys.readouterr().out
    assert "attempting download" in out
    assert "attempted but yfinance returned empty" in out
    # distinct from no-refresh
    assert "no refresh needed" not in out


def test_refresh_attempted_but_no_new_rows_after_dedup(monkeypatch, tmp_path, capsys):
    """yf devuelve filas ya presentes => 'attempted but no new rows after dedup'."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    # yfinance returns overlapping range exactly (all indices already cached)
    df_overlap = _ohlcv_frame(cache_dates[-2:], start_close=100.0)
    # force same index as cached tail
    df_overlap.index = cache_dates[-2:]
    monkeypatch.setattr(di.yf, "download", lambda *a, **kw: df_overlap)

    result = di.download_data("AAPL", start="2026-08-10", end="2026-08-22")
    out = capsys.readouterr().out
    assert "attempted but no new rows after dedup" in out
    # still returns original df
    assert len(result) == len(cache_dates)


# ------------------------------------------------------------------ backfill


def test_backfill_gap_2_triggers_download(monkeypatch, tmp_path, capsys):
    """cache empieza 2026-08-10, request start 2026-08-05 => gap 5 debe disparar backfill."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    old_dates = pd.bdate_range("2026-08-05", "2026-08-09")
    df_old = _ohlcv_frame(old_dates, start_close=50.0)

    calls = {}

    def fake_download(ticker, start=None, end=None, progress=False):
        calls["start"] = start
        calls["end"] = end
        return df_old

    monkeypatch.setattr(di.yf, "download", fake_download)

    result = di.download_data("AAPL", start="2026-08-05", end="2026-08-20")
    assert calls["start"] == "2026-08-05"
    assert calls["end"] == "2026-08-10"
    assert len(result) == len(cache_dates) + len(old_dates)
    out = capsys.readouterr().out
    assert "backfill: gap" in out
    assert "refreshed" in out
    # also refresh gap 0 -> no refresh needed
    assert "refresh: no refresh needed" in out


def test_backfill_gap_0_no_call(monkeypatch, tmp_path, capsys):
    """start == first_date => no backfill attempt."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    # We'll allow refresh to be called with empty to keep test focused;
    # but backfill should NOT call. Use a counter and allow refresh path to return empty.
    calls = {"n": 0}

    def fake_download(ticker, start=None, end=None, progress=False):
        calls["n"] += 1
        # this will be refresh path (since backfill shouldn't trigger)
        # but end=2026-08-20 gap 0 -> actually refresh not triggered either
        return pd.DataFrame()

    monkeypatch.setattr(di.yf, "download", fake_download)

    di.download_data("AAPL", start="2026-08-10", end="2026-08-20")
    # neither backfill nor refresh should have called download (both gaps 0)
    assert calls["n"] == 0
    out = capsys.readouterr().out
    assert "backfill: no backfill needed" in out


def test_backfill_gap_1_triggers(monkeypatch, tmp_path):
    """gap=1 en backfill debe intentar (simetrico a refresh)."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    old_dates = pd.DatetimeIndex([pd.Timestamp("2026-08-09")])
    df_old = _ohlcv_frame(old_dates, start_close=50.0)

    calls = {"n": 0}

    def fake_download(ticker, start=None, end=None, progress=False):
        calls["n"] += 1
        return df_old

    monkeypatch.setattr(di.yf, "download", fake_download)

    di.download_data("AAPL", start="2026-08-09", end="2026-08-20")
    assert calls["n"] == 1


def test_backfill_attempted_but_empty_logs(monkeypatch, tmp_path, capsys):
    """backfill gap>=1 pero yf vacio => señal distincta."""
    di = _patch_cache(monkeypatch, tmp_path)
    cache_dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_cache = _ohlcv_frame(cache_dates)
    df_cache.to_parquet(tmp_path / "AAPL.parquet")

    monkeypatch.setattr(di.yf, "download", lambda *a, **kw: pd.DataFrame())

    di.download_data("AAPL", start="2026-08-05", end="2026-08-20")
    out = capsys.readouterr().out
    assert "backfill: attempted but yfinance returned empty" in out


# ------------------------------------------------------------------ cache miss / edge


def test_cache_miss_full_download(monkeypatch, tmp_path, capsys):
    """sin cache => descarga completa."""
    di = _patch_cache(monkeypatch, tmp_path)
    dates = pd.bdate_range("2026-08-10", "2026-08-20")
    df_full = _ohlcv_frame(dates)

    monkeypatch.setattr(di.yf, "download", lambda *a, **kw: df_full)

    result = di.download_data("AAPL", start="2026-08-10", end="2026-08-20")
    assert len(result) == len(dates)
    out = capsys.readouterr().out
    assert "cache miss" in out
    # parquet should have been written
    assert (tmp_path / "AAPL.parquet").exists()


def test_empty_cache_treated_as_miss(monkeypatch, tmp_path, capsys):
    """cache vacio => tratado como miss, no IndexError."""
    di = _patch_cache(monkeypatch, tmp_path)
    empty = pd.DataFrame({"Open": [], "Close": []})
    empty.index = pd.DatetimeIndex([])
    empty.to_parquet(tmp_path / "AAPL.parquet")

    dates = pd.bdate_range("2026-08-10", "2026-08-12")
    df_full = _ohlcv_frame(dates)
    monkeypatch.setattr(di.yf, "download", lambda *a, **kw: df_full)

    result = di.download_data("AAPL", start="2026-08-10", end="2026-08-12")
    assert len(result) == len(dates)
    out = capsys.readouterr().out
    assert "cache empty" in out
