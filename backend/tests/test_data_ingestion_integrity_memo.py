"""Tests del corte del 531s al hook de integridad.

PRE_REG_REBUILD_531S_MEMOIZE_20260910. Cubren los tres fixes en
`data_ingestion._integrity_hook`:

- (1) memoize por (mtime, size): 2a lectura del MISMO parquet saldea sin red;
      un write real invalida el memo (C1, C4).
- (2) disparador acotado a la ventana movil: hard-flag SOLO historico NO paga
      reconcile; hard-flag en la cola SI (C2).
- (3) known_trading_days: el hook lo propaga a find_intermediate_gaps y
      _known_trading_days_for devuelve la union de fechas del cache (C3).
- (5) el memo devuelve COPIA (sin aliasing) (C5).

Sin red: `yf.download` se parcha a un stub que devuelve el propio parquet
(fresh == cached => sin divergencia => sin re-descarga ni reparacion).
"""

import os

import pandas as pd
import pytest


def _flat_frame(n=40, jump_at=None, jump=1.30, start="2020-01-06"):
    """Frame OHLCV en dias habiles consecutivos, retornos 0 salvo un salto.

    jump_at: posicion donde close pasa de 100 a 100*jump (flag duro si
    jump-1 >= 0.20). None => todos los closes iguales (sin flag).
    """
    idx = pd.bdate_range(start, periods=n)
    close = [100.0] * n
    if jump_at is not None:
        for i in range(jump_at, n):
            close[i] = 100.0 * jump
    return pd.DataFrame(
        {
            "open": list(close),
            "high": [c * 1.001 for c in close],
            "low": [c * 0.999 for c in close],
            "close": close,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """CACHE_DIR -> tmp_path, hook ACTIVO, yf.download -> stub contador."""
    import app.core.data_ingestion as di

    di.CACHE_DIR = str(tmp_path)
    monkeypatch.setattr(di, "INTEGRITY_CHECK_ON_UPDATE", True)
    di._INTEGRITY_MEMO.clear()
    di._KNOWN_DAYS_CACHE.clear()

    calls = {"download": 0, "starts": []}

    def fake_download(ticker, start=None, end=None, progress=False, **kw):
        calls["download"] += 1
        calls["starts"].append(str(start))
        path = os.path.join(str(tmp_path), f"{ticker}.parquet")
        if os.path.exists(path):
            return pd.read_parquet(path)
        return pd.DataFrame()

    monkeypatch.setattr(di.yf, "download", fake_download)
    yield di, calls, tmp_path
    di._INTEGRITY_MEMO.clear()
    di._KNOWN_DAYS_CACHE.clear()


def _write(di, tmp_path, ticker, df):
    path = os.path.join(str(tmp_path), f"{ticker}.parquet")
    df.to_parquet(path)
    return path


# --------------------------------------------------------------- C1 memoize


def test_memo_hit_skips_second_reconcile(sandbox):
    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40, jump_at=39)  # hard-flag en la COLA (en ventana)
    path = _write(di, tmp_path, "FOO", df)

    out1 = di._integrity_hook("FOO", df, path)
    assert calls["download"] >= 1, "1a pasada con hard-flag en ventana reconcilia"

    before = calls["download"]
    out2 = di._integrity_hook("FOO", df, path)  # mismo mtime+size => memo hit
    assert calls["download"] == before, "2a pasada de bytes identicos NO reconcilia"
    assert len(out2) == len(df)
    pd.testing.assert_frame_equal(out1, out2)


def test_memo_invalidated_by_write(sandbox):
    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40, jump_at=39)
    path = _write(di, tmp_path, "FOO", df)

    di._integrity_hook("FOO", df, path)
    assert calls["download"] >= 1
    calls["download"] = 0

    # un write real (append de una rueda) cambia mtime+size => memo cae.
    new_row = _flat_frame(n=1, start=str((df.index[-1] + pd.tseries.offsets.BDay(1)).date()))
    new_row["close"] = [130.0]
    new_row["open"] = [130.0]
    new_row["high"] = [130.13]
    new_row["low"] = [129.87]
    df2 = pd.concat([df, new_row])
    df2.to_parquet(path)

    di._integrity_hook("FOO", df2, path)
    assert calls["download"] >= 1, "tras cambiar el parquet el hook completo corre"


# ----------------------------------------------------------- C2 ventana


def test_historical_hard_flag_does_not_reconcile(sandbox):
    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40, jump_at=3)  # hard-flag lejano (fuera de ventana de 10)
    path = _write(di, tmp_path, "FOO", df)

    di._integrity_hook("FOO", df, path)
    assert calls["download"] == 0, "hard-flag SOLO historico no paga reconcile (fix 2)"


def test_recent_hard_flag_triggers_reconcile(sandbox):
    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40, jump_at=38)  # en la ventana
    path = _write(di, tmp_path, "FOO", df)

    di._integrity_hook("FOO", df, path)
    assert calls["download"] >= 1, "hard-flag en la cola si reconcilia"


# ------------------------------------------------------ C3 known_trading_days


def test_known_trading_days_is_union_of_cache(sandbox):
    di, calls, tmp_path = sandbox
    a = _flat_frame(n=10, start="2021-01-04")
    b = pd.concat([_flat_frame(n=10, start="2021-01-04"),
                   _flat_frame(n=1, start="2021-01-18")])
    _write(di, tmp_path, "AAA", a)
    _write(di, tmp_path, "BBB", b)
    known = di._known_trading_days_for(str(tmp_path))
    assert pd.Timestamp("2021-01-18").date() in known, "union: fecha solo en BBB presente"
    assert pd.Timestamp("2021-01-04").date() in known
    assert len(known) >= 10


def test_hook_passes_known_trading_days_to_gaps(sandbox, monkeypatch):
    di, calls, tmp_path = sandbox
    seen = {}
    import app.core.cache_integrity as ci

    real = ci.find_intermediate_gaps

    def spy(df, known_trading_days=None):
        seen["known"] = known_trading_days
        return real(df, known_trading_days)

    monkeypatch.setattr(ci, "find_intermediate_gaps", spy)
    df = _flat_frame(n=40)  # sin flags => cae al path de huecos
    path = _write(di, tmp_path, "FOO", df)

    di._integrity_hook("FOO", df, path)
    assert "known" in seen, "el hook llama find_intermediate_gaps"
    assert seen["known"] is not None, "el hook pasa known_trading_days (fix 3), no None"
    assert isinstance(seen["known"], set)


# ----------------------------------------------------------------- C5 aliasing


def test_memo_returns_copy_no_aliasing(sandbox):
    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40, jump_at=39)
    path = _write(di, tmp_path, "FOO", df)

    out1 = di._integrity_hook("FOO", df, path)   # corre full y memoiza
    out2 = di._integrity_hook("FOO", df, path)   # memo hit -> copia
    assert out1 is not out2, "el memo devuelve copia, no la misma referencia"
    before = out2["close"].iloc[0]
    out2.loc[out2.index[0], "close"] = 9.99      # mutar la copia entregada
    assert out1["close"].iloc[0] != 9.99, "mutar el df entregado no contamina el memo"
    out3 = di._integrity_hook("FOO", df, path)   # memo hit otra vez
    assert out3["close"].iloc[0] == before, "el memo sigue sano tras mutar una copia"


# ------------------------------------------------------- Concurrencia (load_universe)
#
# `load_universe` corre `download_data` en ThreadPoolExecutor (10 workers). Bajo el
# GIL, dict.get/setitem son atomicos, pero eso no prueba por si solo que el path
# memoizado sea seguro: hay que medir (a) que lecturas concurrentes del memo devuelven
# copias INDEPENDIENTES (que N hilos no contaminan el memo ni se ven entre si al mutar
# lo que cada uno recibe) y (b) que un bulto concurrente sobre memo VACIO (thundering
# herd) no corrompe: todas las salidas correctas, cero red, memo coherente.
#
# Se evita adrede cualquier assert sobre un contador exacto de descargas bajo hilos:
# `calls["download"] += 1` no es atomico y un count seria flaky. Se prueba el INVARIANTE
# (cero red en el path limpio, independencia de copias), no el count.


def test_concurrent_memo_reads_return_independent_copies(sandbox):
    import threading

    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40, jump_at=39)
    path = _write(di, tmp_path, "FOO", df)

    # 1) calentar el memo en un hilo (full una vez, con red), y cerrar la cuenta.
    di._integrity_hook("FOO", df, path)
    assert calls["download"] >= 1
    calls["download"] = 0

    results = []
    errors = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            outs = [di._integrity_hook("FOO", df, path) for _ in range(50)]
            # mutar TODAS las copias entregadas: si alguna compartiera referencia con
            # el memo o con otra, esta contaminacion se propagaria.
            for o in outs:
                o.loc[o.index[0], "close"] = -12345.0
            with lock:
                results.extend(outs)
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors bajo concurrencia: {errors}"
    assert calls["download"] == 0, "el hot path memoizado no reconcilia bajo concurrencia"
    # todas las copias retenidas estan vivas: id() distintos => ninguna es el frame del
    # memo ni alias de otra (si el wrapper devolviera memo[2] directo, colapsaria aqui).
    ids = [id(o) for o in results]
    assert len(ids) == len(set(ids)), "un frame devuelto es alias de otro o del memo"
    # el memo sigue sano tras mutar 400 copias: lectura posterior trae el valor original
    check = di._integrity_hook("FOO", df, path)
    assert check["close"].iloc[0] == float(df["close"].iloc[0]), \
        "mutar copias entregadas no contamina el memo"


def test_concurrent_cold_start_thundering_herd_is_benign(sandbox):
    import threading

    di, calls, tmp_path = sandbox
    df = _flat_frame(n=40)  # sin flags ni huecos: full corre, cero red, memoiza
    path = _write(di, tmp_path, "FOO", df)

    outs = []
    errors = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()  # todas arrancan con el memo VACIO -> solapan el miss
            o = di._integrity_hook("FOO", df, path)
            with lock:
                outs.append(o)
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors bajo concurrencia: {errors}"
    assert calls["download"] == 0, "path limpio: el bulto duplica CPU, no red"
    for o in outs:
        assert len(o) == len(df), "toda salida concurrente es correcta"
    # memo coherente tras la carrera: el bulto converge a una entrada valida
    assert path in di._INTEGRITY_MEMO
    st = os.stat(path)
    memo = di._INTEGRITY_MEMO[path]
    assert memo[0] == st.st_mtime and memo[1] == st.st_size, \
        "el memo guarda un stat coherente con el parquet tras la carrera"

