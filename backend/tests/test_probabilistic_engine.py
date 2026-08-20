"""
T2.1 — PLAN_INTEGRACION_INDICAGENT.md (Fase 2): purge/embargo en WalkForwardValidator.

Verifica que ninguna observación del fold de test caiga dentro de las primeras
`purge_bars` barras después del corte train/test (el forward-return de ese bloque
usa precios que arrancan dentro de la ventana de train).
"""
import numpy as np
import pandas as pd
import pytest

from app.core.probabilistic_engine import SignalQualityMetrics, WalkForwardValidator


def _make_df(n: int = 400, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    signal = rng.normal(0, 1, n)
    return pd.DataFrame(
        {"close": prices, "signal": signal},
        index=np.arange(n, dtype=float),  # índice posicional para asserts exactos
    )


class TestWalkForwardPurge:
    """Cobertura T2.1: embargo de `purge_bars` tras el corte train/test."""

    def _run_capturando_indices(self, monkeypatch, validator: WalkForwardValidator,
                                df: pd.DataFrame, horizon: int,
                                purge_bars: "int | None" = None):
        captured = []

        def fake_ic(signal, forward_returns):
            captured.append(list(signal.index))
            return 0.01

        def noop_ic(signal, forward_returns):  # rank_ic: no capturar dos veces
            return 0.01

        monkeypatch.setattr(SignalQualityMetrics, "compute_ic", staticmethod(fake_ic))
        monkeypatch.setattr(SignalQualityMetrics, "compute_rank_ic", staticmethod(noop_ic))
        result = validator.validate(df, signal_col="signal", return_col="close",
                                    horizon=horizon, purge_bars=purge_bars)
        return result, captured

    def test_purge_default_es_el_horizon(self):
        """purge_bars no provisto → embargo = horizon (criterio de indicAgent)."""
        df = _make_df()
        validator = WalkForwardValidator(train_window=100, test_window=20)
        result = validator.validate(df, "signal", "close", horizon=5)
        assert result["purge_bars"] == 5

    def test_ninguna_observacion_de_test_dentro_del_embargo(self, monkeypatch):
        """Invariante T2.1: para cada fold, todas las filas de test están en o
        después de train_end + purge_bars (nunca dentro del bloque purgado)."""
        horizon = 7
        train_window, test_window = 100, 20
        df = _make_df(n=400)
        validator = WalkForwardValidator(train_window=train_window, test_window=test_window)
        result, captured = self._run_capturando_indices(monkeypatch, validator, df,
                                                        horizon, purge_bars=None)
        assert result["n_windows"] == len(captured) >= 1
        for k, indices in enumerate(captured):
            start = k * test_window
            train_end = start + train_window
            # mínimo índice del fold de test: exactamente el fin del embargo
            assert min(indices) == train_end + horizon
            # ninguna observación dentro del bloque purgado, y todas dentro del fold
            assert all(train_end + horizon <= i < train_end + test_window for i in indices)
            assert max(indices) == train_end + test_window - 1

    def test_purge_bars_0_recupera_el_corte_contiguo_previo(self, monkeypatch):
        """purge_bars=0 → comportamiento pre-2026-08-20 (corte contiguo), para
        reproducir resultados históricos si hiciera falta compararlos."""
        train_window, test_window = 100, 20
        df = _make_df(n=400)
        validator = WalkForwardValidator(train_window=train_window, test_window=test_window)
        result, captured = self._run_capturando_indices(monkeypatch, validator, df,
                                                        horizon=7, purge_bars=0)
        assert result["purge_bars"] == 0
        for k, indices in enumerate(captured):
            start = k * test_window
            assert min(indices) == start + train_window  # contiguo al corte

    def test_purge_explicito_mayor_al_horizon(self, monkeypatch):
        """purge_bars explícito > horizon se respeta tal cual (embargo conservador)."""
        train_window, test_window = 100, 20
        df = _make_df(n=400)
        validator = WalkForwardValidator(train_window=train_window, test_window=test_window)
        result, captured = self._run_capturando_indices(monkeypatch, validator, df,
                                                        horizon=5, purge_bars=9)
        assert result["purge_bars"] == 9
        for k, indices in enumerate(captured):
            train_end = k * test_window + train_window
            assert min(indices) == train_end + 9

    def test_purge_igual_o_mayor_al_test_window_no_crashea(self):
        """Purge >= test_window: el fold de test queda vacío para siempre →
        error elegante, no crash ni ventana con 0 observaciones."""
        df = _make_df(n=400)
        validator = WalkForwardValidator(train_window=100, test_window=20)
        result = validator.validate(df, "signal", "close", horizon=5, purge_bars=20)
        assert result == {"error": "No hay suficientes ventanas"}

    def test_purge_negativo_se_trata_como_cero(self):
        df = _make_df(n=400)
        validator = WalkForwardValidator(train_window=100, test_window=20)
        result = validator.validate(df, "signal", "close", horizon=5, purge_bars=-3)
        assert result["purge_bars"] == 0

    def test_resultado_sigue_reportando_metricas_validas_con_purge(self):
        """Humo end-to-end con el horizonte real del motor (20) sobre test_window
        default (63): aún con embargo quedan >= 20 observaciones por fold (mínimo
        de compute_ic), así que las métricas siguen siendo computables."""
        rng = np.random.RandomState(7)
        n = 2000
        logret = rng.normal(0, 0.01, n)
        prices = 100 * np.exp(np.cumsum(logret))
        fwd = np.roll(logret, -20).cumsum() * 0 + pd.Series(logret).shift(-20).fillna(0).values
        # señal débilmente predictiva del forward return a 20d: retorna + ruido
        fwd_20 = np.array([logret[i:i + 20].sum() if i + 20 <= n else 0.0 for i in range(n)])
        signal = fwd_20 + rng.normal(0, 0.005, n)
        df = pd.DataFrame({"close": prices, "signal": signal},
                          index=np.arange(n, dtype=float))
        validator = WalkForwardValidator()  # 504/63 defaults de producción
        result = validator.validate(df, "signal", "close", horizon=20)
        assert result["purge_bars"] == 20
        assert result["n_windows"] >= 10
        assert isinstance(result["mean_ic"], float)
        assert isinstance(result["icir"], float)
        assert -1.0 <= result["mean_ic"] <= 1.0
        # la señal SÍ es predictiva por construcción → IC medio positivo alto
        assert result["mean_ic"] > 0.3
