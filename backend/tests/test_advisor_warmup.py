"""Tests TASK_WARMUP_PARALELO_20260909 — warmup advisor + load_universe paralelo.

Criterios 1-4 del PRE_REGISTRO_WARMUP.md (el 5 son números reales de cierre,
no test). Requieren TestClient → correr con el venv (httpx), no con el
python del sistema.
"""
import asyncio
import time

import pandas as pd
import pytest

from app.api.routes import advisor


# ------------------------------------------------------------------ helpers

def _tiny_df(n=250, close=100.0):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000,
    }, index=idx)


class _Ctx:
    """Contexto mínimo que warmup_advisor_once necesita de _load_context_sync."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        today = pd.Timestamp.now().normalize()
        return ({}, today, {"state_name": "x"}, 0, None, None, None)


@pytest.fixture(autouse=True)
def _reset_caches():
    """Aislar los caches globales entre tests (son mutables a nivel módulo)."""
    advisor._context_cache = None
    advisor._context_cache_time = 0.0
    advisor._tickets_cache = None
    advisor._tickets_cache_time = 0.0
    advisor._tickets_cache_ctx_time = 0.0
    yield
    advisor._context_cache = None
    advisor._context_cache_time = 0.0
    advisor._tickets_cache = None
    advisor._tickets_cache_time = 0.0
    advisor._tickets_cache_ctx_time = 0.0


# ------------------------------------------------- (a) startup no bloquea

def test_warmup_no_bloquea_startup(monkeypatch):
    """Criterio 1: _load_context_sync lento (6s) → startup() retorna en
    < 5s, el warmup corre en background y health() responde mientras el
    loader sigue corriendo.

    NOTA: el ticket pedía TestClient, pero el venv tiene starlette/httpx
    incompatibles (TestClient.__init__() got 'app' kwarg → TypeError en
    construcción, sin workaround sin tocar deps). Equivalente directo:
    se invoca la corutina startup() + el endpoint health() sin HTTP.
    """
    import threading

    import app.main as main_mod

    # _load_context_sync real tardaría minutos con red; sleep(6) simula
    # un warmup lento sin red ni CPU (el assert es < 5s, sobra margen).
    started = threading.Event()

    def slow_loader():
        started.set()
        time.sleep(6)
        return _Ctx()()

    monkeypatch.setattr(advisor, "_load_context_sync", slow_loader)
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: [])
    # init_db real toca SQLite de dev — no es objeto de este test.
    monkeypatch.setattr(main_mod, "init_db", lambda: None)

    async def scenario():
        # (i) startup retorna sin esperar al warmup
        await asyncio.wait_for(main_mod.startup(), timeout=5.0)
        # (ii) el warmup arrancó en background
        for _ in range(120):
            if started.is_set():
                break
            await asyncio.sleep(0.05)
        assert started.is_set(), "el warmup no arrancó en background"
        # (iii) health responde con el loader todavía corriendo (>1s restan)
        t0 = time.monotonic()
        resp = await main_mod.health()
        dt_s = time.monotonic() - t0
        assert resp["status"] in ("ok", "degraded")
        assert dt_s < 5.0, f"health tardó {dt_s:.1f}s con warmup en curso"
        # Dejar completar el ciclo 1 (~6s) para liberar el lock limpio
        # (cancelar con el lock tomado lo dejaría trabado para otros tests).
        await asyncio.sleep(7)

    asyncio.run(scenario())


# --------------------------------------- (b) TTL nunca se alcanza en caliente

def test_rewarmup_evita_contexto_expirado(monkeypatch):
    """Criterio 2: TTL=2s, re-warmup=1.5s, 3 ciclos → un request posterior
    NO dispara rebuild (el contador de loads no aumenta)."""
    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 2.0)

    ctx = _Ctx()
    monkeypatch.setattr(advisor, "_load_context_sync", ctx)
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: [])

    async def scenario():
        await advisor.warmup_advisor_loop(interval_s=1.5, max_cycles=3)
        n_after_loop = ctx.calls
        assert n_after_loop >= 1
        # Request posterior: debe servirse del cache sin rebuild.
        await advisor._get_context()
        return n_after_loop, ctx.calls

    n_after_loop, n_after_request = asyncio.run(scenario())
    assert n_after_request == n_after_loop, (
        f"rebuild en request caliente: loads {n_after_loop} → {n_after_request}")


# ---------------------------------- (c) paralelo == secuencial + (d) aislado

def _stub_download_data(frames, fail_on=()):
    def stub(ticker, start, end):
        if ticker in fail_on:
            raise RuntimeError(f"yfinance 429 simulado para {ticker}")
        return frames[ticker]
    return stub


def test_load_universe_paralelo_igual_secuencial(monkeypatch):
    """Criterio 3: mismo dict (tickers, orden, valores) que la referencia
    secuencial, con download_data stubbeado."""
    import app.core.data_ingestion as di

    frames = {
        "AAA": _tiny_df(n=250, close=10.0),
        "BBB": _tiny_df(n=250, close=20.0),
        "CCC": _tiny_df(n=30, close=30.0),   # <200 filas → excluido
        "DDD": _tiny_df(n=300, close=40.0),
        "EEE": _tiny_df(n=250, close=50.0),
    }
    monkeypatch.setattr(di, "download_data", _stub_download_data(frames))
    tickers = list(frames)

    # Referencia TRULY secuencial (loop inline, sin threads).
    expected = {}
    for t in tickers:
        df = frames[t]
        if len(df) > 200:
            expected[t] = df

    got = di.load_universe(tickers, "2025-01-01", "2026-01-01", max_workers=4)
    assert list(got.keys()) == list(expected.keys()) == ["AAA", "BBB", "DDD", "EEE"]
    for t in expected:
        pd.testing.assert_frame_equal(got[t], expected[t])


def test_load_universe_fallo_aislado(monkeypatch, capsys):
    """Criterio 4: un ticker que raisea no mata el lote; los exitosos van
    en el dict y el fallo queda logueado."""
    import app.core.data_ingestion as di

    frames = {f"S{i}": _tiny_df(n=250, close=float(i)) for i in range(5)}
    monkeypatch.setattr(di, "download_data",
                        _stub_download_data(frames, fail_on={"S2"}))

    got = di.load_universe(list(frames), "2025-01-01", "2026-01-01", max_workers=3)
    assert sorted(got.keys()) == ["S0", "S1", "S3", "S4"]
    out = capsys.readouterr().out
    assert "S2" in out and "ERROR aislado" in out
    assert "lote fin" in out
