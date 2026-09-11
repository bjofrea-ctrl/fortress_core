"""Tests TASK_SWR_ADVISOR_20260911 — stale-while-revalidate en /universe.

Criterios del PRE_REGISTRO_SWR_ADVISOR_20260911.md (todos con FakeClock
determinista + locks reales tomados a mano para simular el rebuild):
1. rebuild en curso + par previo → viejo en <1s, is_stale=True, sin disco.
2. cold start (sin par) → bloquea y rebuilda, is_stale=False.
3. flag is_stale explícito y honesto en ambos caminos.
4. nunca mezcla de generaciones (tickets.ctx_time == ctx gen servido).
"""
import asyncio
import time
from types import SimpleNamespace

import pandas as pd
import pytest
from app.api.routes import advisor


@pytest.fixture(autouse=True)
def _reset_caches():
    """Aislar los caches globales entre tests (son mutables a nivel módulo)."""
    advisor._context_cache = None
    advisor._context_cache_time = 0.0
    advisor._tickets_cache = None
    advisor._tickets_cache_time = 0.0
    advisor._tickets_cache_ctx_time = 0.0
    advisor._last_complete_pair = None
    yield
    advisor._context_cache = None
    advisor._context_cache_time = 0.0
    advisor._tickets_cache = None
    advisor._tickets_cache_time = 0.0
    advisor._tickets_cache_ctx_time = 0.0
    advisor._last_complete_pair = None


# ------------------------------------------------------------------ helpers

class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _tiny_df():
    # bdate_range salta el finde: 01,02,03,04,07 → last_cache = 2026-09-07.
    idx = pd.bdate_range("2026-09-01", periods=5)
    return pd.DataFrame({"close": [100.0] * 5}, index=idx)


def _ctx_tuple(today=None, regime_name="VIEJO"):
    return (
        {"AAA": _tiny_df()},
        today or pd.Timestamp("2026-09-09"),
        {"state_name": regime_name, "confidence": 0.9},
        1, None, None, None,
    )


def _tickets_old():
    return [{"symbol": "AAA", "state": "VIGILAR", "win_prob": 0.5}]


# --------------------------------------- (1) rebuild en curso → par viejo <1s

def test_swr_sirve_par_anterior_durante_rebuild(monkeypatch, tmp_path):
    """Criterio 1: locks tomados (rebuild en curso) + par previo vencido →
    sirve el par viejo en <1s real, is_stale=True, sin tocar disco."""
    clock = _FakeClock()
    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 300.0)
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH",
                        str(tmp_path / "decision_states.json"))

    async def fake_threadpool(func, *args):
        return func(*args)

    monkeypatch.setattr(advisor, "run_in_threadpool", fake_threadpool)
    monkeypatch.setattr(advisor, "_load_context_sync", lambda: _ctx_tuple())
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: _tickets_old())
    monkeypatch.setattr(advisor, "_cache_date",
                        lambda: pd.Timestamp("2026-09-09"))

    async def scenario():
        # Poblar caches + publicar el par (warmup exitoso a t=0).
        await advisor.warmup_advisor_once()
        assert advisor._last_complete_pair is not None
        # El TTL pasa sin rebuild (idle): el par queda vencido.
        clock.advance(305.0)
        # El warmup arranca su rebuild y TOMA los locks: simularlo.
        await advisor._context_lock.acquire()
        await advisor._tickets_lock.acquire()
        try:
            # Probar que el camino SWR no toca disco: _cache_date revienta.
            monkeypatch.setattr(
                advisor, "_cache_date",
                lambda: (_ for _ in ()).throw(AssertionError("disco en camino SWR")))
            t0 = time.perf_counter()
            body = await asyncio.wait_for(advisor.advisor_universe(), timeout=10)
            dt = time.perf_counter() - t0
        finally:
            advisor._context_lock.release()
            advisor._tickets_lock.release()
        return body, dt

    body, dt = asyncio.run(scenario())
    assert dt < 1.0, f"bloqueó {dt:.2f}s durante rebuild en curso"
    assert body["is_stale"] is True
    assert [t["symbol"] for t in body["states"]] == ["AAA"]
    assert body["staleness"]["last_cache"] == "2026-09-07"


# --------------------------------- (2) cold start bloquea y rebuilda (fresco)

def test_swr_cold_start_bloquea_y_devuelve_fresco(monkeypatch, tmp_path):
    """Criterio 2: sin par previo (cold start real) no hay nada que servir:
    el request ESPERA al rebuild y devuelve payload fresco, is_stale=False."""
    clock = _FakeClock()
    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 300.0)
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH",
                        str(tmp_path / "decision_states.json"))

    loads = []

    def slow_loader():
        loads.append(clock.now)
        clock.advance(5.0)  # rebuild lento: el request debe esperarlo
        return _ctx_tuple()

    async def fake_threadpool(func, *args):
        return func(*args)

    monkeypatch.setattr(advisor, "run_in_threadpool", fake_threadpool)
    monkeypatch.setattr(advisor, "_load_context_sync", slow_loader)
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: _tickets_old())
    monkeypatch.setattr(advisor, "_cache_date",
                        lambda: pd.Timestamp("2026-09-09"))

    async def scenario():
        assert advisor._last_complete_pair is None
        body = await asyncio.wait_for(advisor.advisor_universe(), timeout=10)
        return body

    body = asyncio.run(scenario())
    assert loads == [0.0], "debió rebuildar una vez (bloqueante)"
    assert [t["symbol"] for t in body["states"]] == ["AAA"]
    assert body["is_stale"] is False


# --------------------------- (4) sin mezcla de generaciones en fase tickets

def test_swr_no_mezcla_contexto_nuevo_con_tickets_viejos(monkeypatch, tmp_path):
    """Criterio 4: warmup en FASE TICKETS (ctx nuevo ya cacheado, tickets lock
    tomado rebuildando para la gen nueva): el endpoint sirve el par VIEJO
    completo — nunca contexto nuevo + tickets viejos."""
    clock = _FakeClock()
    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 300.0)
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH",
                        str(tmp_path / "decision_states.json"))
    monkeypatch.setattr(advisor, "_cache_date",
                        lambda: (_ for _ in ()).throw(AssertionError("disco en camino SWR")))

    old_ctx = _ctx_tuple(regime_name="VIEJO")
    new_ctx = _ctx_tuple(regime_name="NUEVO")
    old_tickets = _tickets_old()

    async def scenario():
        # Estado simulado de mitad de rebuild de tickets: contexto NUEVO ya
        # cacheado y fresco, tickets lock tomado rebuildando para la gen nueva.
        advisor._context_cache = new_ctx
        advisor._context_cache_time = 100.0
        advisor._tickets_cache = old_tickets
        advisor._tickets_cache_time = 0.0
        advisor._tickets_cache_ctx_time = 0.0  # gen VIEJA != gen nueva
        advisor._last_complete_pair = (old_ctx, old_tickets, 0.0)
        clock.advance(400.0)  # par viejo vencido (edad 400 > TTL 300)
        await advisor._tickets_lock.acquire()
        try:
            body = await asyncio.wait_for(advisor.advisor_universe(), timeout=10)
        finally:
            advisor._tickets_lock.release()
        return body

    body = asyncio.run(scenario())
    assert body["regime"]["name"] == "VIEJO", "mezcló contexto nuevo con tickets viejos"
    assert [t["symbol"] for t in body["states"]] == ["AAA"]
    assert body["is_stale"] is True


# -------------------------------- (3/5) camino normal intacto + flag honesto

def test_universe_normal_sin_rebuild_en_curso(monkeypatch, tmp_path):
    """Criterios 3 y 5: sin contención, el camino bloqueante responde fresco
    con is_stale=False y el contrato intacto (staleness de disco como antes).
    """
    clock = _FakeClock()
    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 300.0)
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH",
                        str(tmp_path / "decision_states.json"))

    async def fake_threadpool(func, *args):
        return func(*args)

    monkeypatch.setattr(advisor, "run_in_threadpool", fake_threadpool)
    monkeypatch.setattr(advisor, "_load_context_sync", lambda: _ctx_tuple())
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: _tickets_old())
    monkeypatch.setattr(advisor, "_cache_date",
                        lambda: pd.Timestamp("2026-09-09"))

    async def scenario():
        return await asyncio.wait_for(advisor.advisor_universe(), timeout=10)

    body = asyncio.run(scenario())
    assert body["is_stale"] is False
    assert body["as_of"] == "2026-09-09"
    assert body["regime"]["name"] == "VIEJO"
    assert [t["symbol"] for t in body["states"]] == ["AAA"]
    assert body["staleness"]["last_cache"] == "2026-09-09"
    assert "honesty_badge" in body and "risk_params" in body
