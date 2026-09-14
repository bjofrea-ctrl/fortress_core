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
    """Criterio 2 (regression guard): tras 3 ciclos del loop, un request
    posterior NO dispara rebuild (el contador de loads no aumenta) — el loop
    mantiene el cache caliente.

    Determinista vía FakeClock: la versión con reloj real era flaky bajo
    carga (falló en la suite completa 2026-09-10): el gap entre el gen del
    último ciclo y la request final incluye el scan de `_cache_date()`
    (~110 parquet reales) — con TTL=2s real, esa pausa superaba el TTL y la
    request reconstruía sin que nada estuviera roto.

    NOTA: este test NO detecta el bug del ciclo lento (por eso existe
    test_rewarmup_ciclo_lento_sin_ventana_fria): con ciclos instantáneos
    cualquier intervalo < TTL despertaba antes del vencimiento.
    """
    from types import SimpleNamespace

    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    clock = FakeClock()

    async def fake_sleep(delay):
        clock.advance(delay)

    async def fake_threadpool(func, *args):
        return func(*args)

    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 2.0)
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "asyncio",
                        SimpleNamespace(sleep=fake_sleep, Lock=asyncio.Lock))
    monkeypatch.setattr(advisor, "run_in_threadpool", fake_threadpool)

    ctx = _Ctx()
    monkeypatch.setattr(advisor, "_load_context_sync", ctx)
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: [])
    monkeypatch.setattr(advisor, "_cache_date", lambda: None)

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


def test_rewarmup_ciclo_lento_sin_ventana_fria(monkeypatch):
    """FIX criterio 2 (hallazgo OpenCode 2026-09-10): el sleep del loop contaba
    desde el FIN del ciclo. Con un rebuild lento (531s real > TTL 300s) el
    próximo re-warmup caía DESPUÉS del vencimiento → ventana fría donde todo
    request pagaba rebuild. Los tests originales no lo veían porque stubbeaban
    ciclos instantáneos: con ciclo instantáneo, intervalo fijo < TTL siempre
    alcanza a despertar antes del vencimiento.

    Escenario (reloj fake, todo determinista): TTL=4s, rebuild de contexto
    = 2s (LENTO, no instantáneo), tickets instantáneos, 3 ciclos.

    Propiedad que falsa el bug: el rebuild N+1 arranca EXACTAMENTE cuando
    vence el cache N (gen+TTL) — nunca queda un cache vencido esperando al
    próximo ciclo programado. Con el sleep post-ciclo original estos números
    daban rebuild 2 a los 6.5s (venció a 6.0): 0.5s de ventana fría; en
    producción 531+280-300 = 511s (~8.5min).
    """
    from types import SimpleNamespace

    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    clock = FakeClock()
    rebuild_starts = []   # instante (reloj fake) en que arrancó cada rebuild
    gens = []             # _context_cache_time tras cada rebuild (fin del load)
    sleep_delays = []

    def slow_loader():
        rebuild_starts.append(clock.now)
        clock.advance(2.0)  # el ciclo NO es instantáneo — acá estaba el bug
        gens.append(clock.now)
        today = pd.Timestamp.now().normalize()
        return ({}, today, {"state_name": "x"}, 0, None, None, None)

    async def fake_sleep(delay):
        sleep_delays.append(delay)
        clock.advance(delay)

    async def fake_threadpool(func, *args):
        return func(*args)

    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 4.0)
    # Parchear el binding del módulo (no el stdlib): advisor solo usa
    # time.monotonic / asyncio.sleep en este camino.
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "asyncio",
                        SimpleNamespace(sleep=fake_sleep, Lock=asyncio.Lock))
    monkeypatch.setattr(advisor, "run_in_threadpool", fake_threadpool)
    monkeypatch.setattr(advisor, "_load_context_sync", slow_loader)
    monkeypatch.setattr(advisor, "_build_tickets_sync", lambda *a: [])
    monkeypatch.setattr(advisor, "_cache_date", lambda: None)

    async def scenario():
        await advisor.warmup_advisor_loop(interval_s=1.5, max_cycles=3)
        # Request ANTES del vencimiento del último cache: debe ser hot.
        clock.advance(3.9)
        await advisor._get_context()
        return len(rebuild_starts), sleep_delays

    n_loads, delays = asyncio.run(scenario())

    # (1) Cada ciclo despertó a gen+TTL y encontró el cache JUSTO vencido:
    # todos los ciclos hicieron rebuild real (cero hits inútiles).
    assert n_loads == 3, f"ciclos que no rebuildaron: {n_loads}/3"
    # (2) LA propiedad sin-gap: rebuild N+1 == vencimiento del cache N.
    assert rebuild_starts[1] == gens[0] + 4.0, (
        f"ventana fría: cache 1 venció a {gens[0] + 4.0} "
        f"y el rebuild 2 arrancó a {rebuild_starts[1]}")
    assert rebuild_starts[2] == gens[1] + 4.0, (
        f"ventana fría: cache 2 venció a {gens[1] + 4.0} "
        f"y el rebuild 3 arrancó a {rebuild_starts[2]}")
    # (3) El delay se ancló al vencimiento (4.0 = TTL, ciclo de 2.0 desde
    # gen 2.0): no es el intervalo fijo de 1.5 del loop viejo.
    assert delays == [4.0, 4.0], f"delays del loop: {delays}"
    # (4) La request previa al vencimiento fue hot (no sumó rebuild).
    assert n_loads == 3 and len(rebuild_starts) == 3


def test_rewarmup_piso_minimo_evita_spin(monkeypatch):
    """Patología pre-declarada (rebuild > TTL): el ciclo termina DESPUÉS del
    vencimiento de su propio contexto (contexto instantáneo + tickets de 3s
    con TTL 2s). El delay anclado al vencimiento sale NEGATIVO: sin piso, el
    loop despertaría a los 0s en spin de ciclos hit (regresión del intento
    intermedio max(0, interval-elapsed), que daba delay 0 exacto acá).

    El piso interval_s garantiza dormir >= interval_s entre ciclos.
    """
    from types import SimpleNamespace

    class FakeClock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    clock = FakeClock()
    sleep_delays = []

    def loader():
        today = pd.Timestamp.now().normalize()
        return ({}, today, {"state_name": "x"}, 0, None, None, None)

    def slow_tickets(*a):
        clock.advance(3.0)  # ciclo total 3.0 > TTL 2.0
        return []

    async def fake_sleep(delay):
        assert delay > 0, "delay 0: el loop entraría en spin"
        sleep_delays.append(delay)
        clock.advance(delay)

    async def fake_threadpool(func, *args):
        return func(*args)

    monkeypatch.setattr(advisor, "_CONTEXT_CACHE_TTL_SECONDS", 2.0)
    monkeypatch.setattr(advisor, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(advisor, "asyncio",
                        SimpleNamespace(sleep=fake_sleep, Lock=asyncio.Lock))
    monkeypatch.setattr(advisor, "run_in_threadpool", fake_threadpool)
    monkeypatch.setattr(advisor, "_load_context_sync", loader)
    monkeypatch.setattr(advisor, "_build_tickets_sync", slow_tickets)
    monkeypatch.setattr(advisor, "_cache_date", lambda: None)

    async def scenario():
        await advisor.warmup_advisor_loop(interval_s=1.5, max_cycles=2)

    asyncio.run(scenario())
    assert sleep_delays == [1.5], (
        f"debe dormir >= interval_s (1.5), durmió {sleep_delays}")


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
