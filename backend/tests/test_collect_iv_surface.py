"""Tests B2 — colector de superficie IV (PLAN_REMEDIO_BRECHAS_20260903).

Contract de datos y ciclo de vida del snapshot, TODO con un fake de
yfinance inyectado (sin red). El fake replica exactamente el contract
verificado en vivo contra yfinance 1.2.0 el 2026-09-03 (probe SPY:
t.options -> tupla de expiries; t.option_chain(exp) -> objeto con
.calls/.puts, columnas contractSymbol/strike/lastPrice/bid/ask/
impliedVolatility/openInterest/volume/inTheMoney).
"""
import datetime as dt
import os
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import collect_iv_surface as civ  # noqa: E402

# ------------------------------------------------------------------ fake yf

def _chain_df(n=3):
    """DataFrame con las columnas EXACTAS del contract yfinance 1.2.0."""
    return pd.DataFrame({
        "contractSymbol": [f"TST{x}260904C00100000" for x in range(n)],
        "lastTradeDate": ["2026-09-03 3:59PM EDT"] * n,
        "strike": [100.0 + i * 5 for i in range(n)],
        "lastPrice": [10.0, 9.0, 8.0],
        "bid": [9.9, 8.9, 7.9],
        "ask": [10.1, 9.1, 8.1],
        "change": [0.1, -0.1, 0.0],
        "percentChange": [1.0, -1.0, 0.0],
        "volume": [100, 50, 25],
        "openInterest": [200, 150, 75],
        "impliedVolatility": [0.25, 0.28, 0.31],
        "inTheMoney": [True, False, False],
        "contractSize": ["REGULAR"] * n,
        "currency": ["USD"] * n,
    })


# Expiries del FakeTicker RELATIVAS al hoy real: la suite nunca envejece.
# (Bug de auditoría 2026-09-05: expiries absolutas fijas quedaban en el
# pasado al día siguiente y el dte daba negativo — `main` usa reloj real.)
def _fake_expiries():
    return tuple((dt.date.today() + dt.timedelta(days=d)).isoformat()
                 for d in (1, 8, 15, 43))


class FakeTicker:
    """Ticker fake con expiries siempre futuras (relativas al hoy real)."""

    def __init__(self, symbol):
        self.symbol = symbol

    options = _fake_expiries()

    def option_chain(self, exp):
        return SimpleNamespace(calls=_chain_df(), puts=_chain_df())


class FakeTickerEmpty:
    def __init__(self, symbol):
        self.symbol = symbol

    options = ()

    def option_chain(self, exp):  # pragma: no cover — nunca llega
        raise AssertionError("sin expiries no se pide cadena")


# ------------------------------------------------------------- collect_symbol

class TestCollectSymbol:
    def test_estructura_fila_una_por_contrato(self, monkeypatch):
        monkeypatch.setattr("yfinance.Ticker", FakeTicker)
        df = civ.collect_symbol("SPY", spot=500.0, max_expiries=2, sleep_s=0)
        # 2 expiries x (calls 3 + puts 3) = 12 filas
        assert len(df) == 12
        cols = set(df.columns)
        for c in ("symbol", "option_type", "expiry", "dte", "strike", "last",
                  "bid", "ask", "implied_volatility", "open_interest",
                  "volume", "in_the_money", "spot", "snapshot_date"):
            assert c in cols, f"falta columna {c}"
        assert set(df["option_type"]) == {"call", "put"}
        assert (df["symbol"] == "SPY").all()
        assert (df["spot"] == 500.0).all()
        # expiries relativas al hoy real -> dte positivo SIEMPRE (1 y 8 días)
        assert sorted(df["dte"].unique()) == [1, 8]
        assert (df["snapshot_date"] == dt.date.today().isoformat()).all()
        # renombres correctos del contract yfinance
        assert "lastPrice" not in cols and "last" in cols
        assert "impliedVolatility" not in cols and "implied_volatility" in cols
        assert "openInterest" not in cols and "open_interest" in cols

    def test_today_inyectable_determinista(self, monkeypatch):
        """Guardián del bug de auditoría: `today` inyectable fija el dte y el
        snapshot_date sin tocar el reloj global — mismo mecanismo que
        compensa expiries fijas de un fixture contra cualquier fecha."""
        hoy_fijo = dt.datetime(2026, 9, 3)

        class FakeTickerFijo:
            options = ("2026-09-04", "2026-09-11")

            def __init__(self, symbol):
                self.symbol = symbol

            def option_chain(self, exp):
                return SimpleNamespace(calls=_chain_df(), puts=_chain_df())

        monkeypatch.setattr("yfinance.Ticker", FakeTickerFijo)
        df = civ.collect_symbol("SPY", spot=500.0, max_expiries=2, sleep_s=0,
                                today=hoy_fijo)
        assert sorted(df["dte"].unique()) == [1, 8]  # contra el hoy inyectado
        assert (df["snapshot_date"] == "2026-09-03").all()

    def test_max_expiries_limita_el_snapshot(self, monkeypatch):
        monkeypatch.setattr("yfinance.Ticker", FakeTicker)
        df = civ.collect_symbol("SPY", spot=500.0, max_expiries=1, sleep_s=0)
        assert df["expiry"].nunique() == 1

    def test_simbolo_sin_expiries_falla_visible(self, monkeypatch):
        monkeypatch.setattr("yfinance.Ticker", FakeTickerEmpty)
        with pytest.raises(RuntimeError, match="sin expiries"):
            civ.collect_symbol("XYZ", spot=10.0, max_expiries=2, sleep_s=0)


# ------------------------------------------------------------------ spot local

class TestSpotLocal:
    def test_spot_desde_cache_local_case_insensitive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(civ, "DAILY_CACHE_DIR", tmp_path)
        # parquet con columnas lowercase (post-saneo A0)
        df = pd.DataFrame({"close": [99.0, 100.5], "volume": [1, 2]},
                          index=pd.DatetimeIndex(
                              [pd.Timestamp("2026-09-02"), pd.Timestamp("2026-09-03")]))
        df.to_parquet(tmp_path / "AAPL.parquet")
        assert civ._spot_from_local_cache("AAPL") == 100.5

    def test_spot_titlecase_compat(self, tmp_path, monkeypatch):
        """Parquets viejos (pre-saneo) con columnas TitleCase también funcionan."""
        monkeypatch.setattr(civ, "DAILY_CACHE_DIR", tmp_path)
        df = pd.DataFrame({"Close": [99.0, 100.5]},
                          index=pd.DatetimeIndex(
                              [pd.Timestamp("2026-09-02"), pd.Timestamp("2026-09-03")]))
        df.to_parquet(tmp_path / "AAPL.parquet")
        assert civ._spot_from_local_cache("AAPL") == 100.5

    def test_spot_sin_parquet_devuelve_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(civ, "DAILY_CACHE_DIR", tmp_path)
        assert civ._spot_from_local_cache("NOEXISTE") is None


# ---------------------------------------------------------------- ciclo de vida

class TestMainLifecycle:
    def _seed_spot(self, tmp_path, monkeypatch, symbols):
        monkeypatch.setattr(civ, "DAILY_CACHE_DIR", tmp_path)
        monkeypatch.setattr(civ, "snapshot_path",
                            lambda day: tmp_path / "iv_surface" / "iv_snapshot_TEST.parquet"
                            if False else (tmp_path / "iv_surface") / f"iv_snapshot_{day.strftime('%Y%m%d')}.parquet")
        for s in symbols:
            (tmp_path / "iv_surface").mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame({"close": [100.0]},
                              index=pd.DatetimeIndex([pd.Timestamp(dt.date.today())]))
            df.to_parquet(tmp_path / f"{s}.parquet")

    def test_run_completo_escribe_parquet_del_dia(self, tmp_path, monkeypatch):
        self._seed_spot(tmp_path, monkeypatch, ["SPY", "QQQ"])
        monkeypatch.setattr("yfinance.Ticker", FakeTicker)
        rc = civ.main(["--symbols", "SPY,QQQ", "--sleep-s", "0",
                       "--max-expiries", "2"])
        assert rc == 0
        out = tmp_path / "iv_surface" / f"iv_snapshot_{dt.date.today().strftime('%Y%m%d')}.parquet"
        assert out.exists()
        df = pd.read_parquet(out)
        assert set(df["symbol"].unique()) == {"SPY", "QQQ"}
        # 2 expiries x (3 calls + 3 puts) = 24 por símbolo, 48 con 2 símbolos
        assert len(df) == 2 * (2 * 6)

    def test_fallo_de_un_simbolo_no_corta_y_reporta(self, tmp_path, monkeypatch):
        self._seed_spot(tmp_path, monkeypatch, ["SPY", "QQQ"])

        class HalfBrokenTicker(FakeTicker):
            def __init__(self, symbol):
                super().__init__(symbol)
                if symbol == "QQQ":
                    raise RuntimeError("delisted / rate limited")

        monkeypatch.setattr("yfinance.Ticker", HalfBrokenTicker)
        rc = civ.main(["--symbols", "SPY,QQQ", "--sleep-s", "0"])
        assert rc == 0  # SPY OK alcanza para el snapshot del día
        df = pd.read_parquet(
            tmp_path / "iv_surface" / f"iv_snapshot_{dt.date.today().strftime('%Y%m%d')}.parquet")
        assert set(df["symbol"].unique()) == {"SPY"}  # QQQ falló visiblemente

    def test_todos_fallidos_no_escribe_parquet(self, tmp_path, monkeypatch):
        self._seed_spot(tmp_path, monkeypatch, ["QQQ"])
        monkeypatch.setattr("yfinance.Ticker", FakeTickerEmpty)
        rc = civ.main(["--symbols", "QQQ", "--sleep-s", "0"])
        assert rc == 1
        out = tmp_path / "iv_surface" / f"iv_snapshot_{dt.date.today().strftime('%Y%m%d')}.parquet"
        assert not out.exists()  # sin datos NO hay snapshot: nada falso en disco

    def test_run_sin_spot_no_intenta_red(self, tmp_path, monkeypatch):
        # cache sin el símbolo -> fail ANTES de construir Ticker
        def boom(symbol):
            raise AssertionError("sin spot no se debe tocar yfinance")
        monkeypatch.setattr(civ, "DAILY_CACHE_DIR", tmp_path)
        monkeypatch.setattr("yfinance.Ticker", boom)
        (tmp_path / "iv_surface").mkdir(parents=True, exist_ok=True)
        civ.snapshot_path = lambda day: (tmp_path / "iv_surface") / f"iv_snapshot_{day.strftime('%Y%m%d')}.parquet"
        rc = civ.main(["--symbols", "GHOST", "--sleep-s", "0"])
        assert rc == 1  # 0 OK, 1 FAIL

    def test_resume_completa_simbolos_faltantes_del_dia(self, tmp_path, monkeypatch):
        self._seed_spot(tmp_path, monkeypatch, ["SPY", "QQQ"])

        class OnlySpyTicker(FakeTicker):
            def __init__(self, symbol):
                if symbol != "SPY":
                    raise RuntimeError("fail primera pasada")

        monkeypatch.setattr("yfinance.Ticker", OnlySpyTicker)
        civ.main(["--symbols", "SPY,QQQ", "--sleep-s", "0"])  # SPY OK, QQQ fail
        # segunda pasada con QQQ sano + --resume: NO re-colecta SPY
        calls = []
        orig_ticker = FakeTicker

        class CountingTicker(orig_ticker):
            def __init__(self, symbol):
                calls.append(symbol)
                super().__init__(symbol)

        monkeypatch.setattr("yfinance.Ticker", CountingTicker)
        rc = civ.main(["--symbols", "SPY,QQQ", "--sleep-s", "0", "--resume"])
        assert rc == 0
        assert calls == ["QQQ"]  # SPY ya estaba: no se re-pide
        df = pd.read_parquet(
            tmp_path / "iv_surface" / f"iv_snapshot_{dt.date.today().strftime('%Y%m%d')}.parquet")
        assert set(df["symbol"].unique()) == {"SPY", "QQQ"}  # día completo


# ----------------------------------------------------------- fuente canónica

class TestSymbolList:
    """Bug de auditoría 2026-09-05: IV_SYMBOLS era una TERCERA lista paralela
    (26/30 comunes con B1) que se desincronizó — MRVL/AMAT/LRCX/PANW fallaban
    "sin spot" en caches que descargan por opportunities_universe. El
    contrato ahora: IV_SYMBOLS ES la lista staged de B1, una sola fuente.

    En worktrees sin B1 el colector cae al fallback (SYMBOLS del universo)
    con warning — los tests de forma (30/SPY/QQQ) solo se exigen donde B1
    vive; el skip es visible en el reporte, no un verde falso."""

    def test_30_unicos_con_spy_qqq_primero(self):
        if "collect_intraday_1min" not in sys.modules:
            pytest.skip("sin B1 en este worktree — fallback activo (universo)")
        assert len(civ.IV_SYMBOLS) == 30
        assert civ.IV_SYMBOLS[0] == "SPY" and civ.IV_SYMBOLS[1] == "QQQ"
        assert len(set(civ.IV_SYMBOLS)) == 30  # sin duplicados

    def test_es_la_misma_lista_staged_de_b1(self):
        """IV_SYMBOLS debe SER STAGED_SYMBOLS de B1 (una sola fuente canónica).

        importorskip: en worktrees sin B1 (viejos) el test se salta — el
        colector corre en el repo real, donde B1 existe y la comparación es
        exigida. Un SKIP aquí es visible en el reporte, no un verde falso.
        """
        mod = pytest.importorskip(
            "scripts.collect_intraday_1min",
            reason="B1 (collect_intraday_1min) no está en este worktree — "
                   "correr donde vive B1 para exigir la identidad de listas")
        assert list(civ.IV_SYMBOLS) == list(mod.STAGED_SYMBOLS)

    def test_subconjunto_del_universo_descargable(self):
        """Todo símbolo del snapshot debe tener parquet diario descargable por
        el updater (universo 102) — sin esto, spots faltantes garantizados."""
        from app.api.routes.opportunities_universe import SYMBOLS as U102
        fuera = [s for s in civ.IV_SYMBOLS if s not in U102]
        assert fuera == [], f"IV_SYMBOLS fuera del universo descargable: {fuera}"
