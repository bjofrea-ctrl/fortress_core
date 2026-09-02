"""Tests de T0.2 — ejecución con lag (PLAN_INTEGRACION_INDICAGENT.md).

El motor end-of-day calcula la señal con el cierre de 'date' pero, con
execution_lag_days=1 (default nuevo), ejecuta en la APERTURA de la barra
siguiente ('date+1'). execution_lag_days=0 conserva el comportamiento ANTERIOR
(el bug): señal y ejecución comparten la misma barra (cierre de 'date').

Estos tests arman un panel sintético determinístico que dispara UNA señal un
lunes conocido, le inyectan un gap overnight grande y verificado en el martes,
y comprueban que el precio de entrada registrado es la apertura del día
siguiente y NO el cierre del día de la señal.
"""
import numpy as np
import pandas as pd
import pytest
from app.core.backtest_engine import BacktestEngine
from app.core.indicators import calculate_all_indicators

SIGNAL_MONDAY = pd.Timestamp("2021-05-10")   # único lunes que dispara señal en el panel
NEXT_DAY = pd.Timestamp("2021-05-11")        # martes, apertura de ejecución
SLIPPAGE = 0.0005

# Tickers que el GlobalRegimeClassifier usa como features — el backtest los
# necesita para fittear/predict el régimen.
_MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]


def _build_panel(n=1000, seed=1, base=100.0, slope=0.10, chop_amp=7.0, chop_freq=0.03):
    """Panel sintético con tendencia sostenida + ondulaciones periódicas.

    Determinístico (mismo seed + HMM random_state=42) y calibrado para que
    generate_signal dispare exactamente un lunes (2021-05-10) a través del
    MISMO camino que corre run() (indicadores ya calculados pasados a
    generate_signal, que los recalcula internamente).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    trend = base * (1 + slope * t / 252)
    chop = chop_amp * np.sin(2 * np.pi * chop_freq * t)
    noise = rng.normal(0, 0.4, n)
    price = trend + chop + np.cumsum(noise)
    price = np.maximum(price, 5.0)
    dates = pd.bdate_range("2019-01-01", periods=n)
    return pd.DataFrame(
        {
            "open": price * 0.9995,
            "high": price * 1.003,
            "low": price * 0.997,
            "close": price,
            "volume": np.full(n, 3_000_000.0),
        },
        index=dates,
    )


def _run(price_data, market_data, lag):
    engine = BacktestEngine(initial_capital=25000)
    return engine.run(
        price_data,
        market_data,
        pd.Timestamp("2021-01-01"),
        pd.Timestamp("2021-12-31"),
        execution_lag_days=lag,
    )


def _gap_panel():
    """Panel con un gap overnight conocido (+5% de apertura a apertura).

    El lunes 2021-05-10 cierra en 'close'; el martes 2021-05-11 abre un 5%
    por encima de ese cierre. Así el precio de entrada con lag=1 debe ser la
    apertura del martes (con gap) y NO el cierre del lunes.
    """
    panel = _build_panel()
    monday_close = float(panel.loc[SIGNAL_MONDAY, "close"])
    panel.loc[NEXT_DAY, "open"] = monday_close * 1.05
    return panel, monday_close


def _market_data():
    base = _build_panel()
    return {t: base.copy() for t in _MARKET_TICKERS}


def test_entrada_con_lag_1_se_ejecuta_en_apertura_del_dia_siguiente():
    panel, monday_close = _gap_panel()
    res = _run({"SYN": panel}, _market_data(), lag=1)

    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    # Se ejecuta el martes (día siguiente al lunes de señal)...
    assert trade["entry_date"] == NEXT_DAY
    # ... al PRECIO DE APERTURA del martes (que tiene el gap +5%), no al cierre
    # del lunes que generó la señal.
    assert trade["entry_price"] == pytest.approx(float(panel.loc[NEXT_DAY, "open"]), abs=1e-6)
    assert trade["entry_price"] != pytest.approx(monday_close, abs=1e-6)


def test_entrada_con_lag_0_conserva_ejecucion_en_cierre_de_la_senial():
    panel, monday_close = _gap_panel()
    res = _run({"SYN": panel}, _market_data(), lag=0)

    assert len(res["trades"]) == 1
    trade = res["trades"][0]
    # Comportamiento ANTERIOR (el bug): señal y ejecución en la MISMA barra.
    assert trade["entry_date"] == SIGNAL_MONDAY
    assert trade["entry_price"] == pytest.approx(monday_close, abs=1e-6)


def test_salida_con_lag_1_usa_apertura_del_dia_siguiente_no_cierre():
    # Un stop/target detectado con el cierre de 'date' se ejecuta en la apertura
    # de 'date+1'. Invariante: exit_price = open[exit_date]*(1-slippage) con
    # lag=1, y = close[exit_date]*(1-slippage) con lag=0.
    panel, _ = _gap_panel()
    ind = calculate_all_indicators(panel)

    res1 = _run({"SYN": panel}, _market_data(), lag=1)
    trade1 = res1["trades"][0]
    assert trade1["exit_price"] == pytest.approx(
        float(ind.loc[trade1["exit_date"], "open"]) * (1 - SLIPPAGE), abs=1e-6
    )

    res0 = _run({"SYN": panel}, _market_data(), lag=0)
    trade0 = res0["trades"][0]
    assert trade0["exit_price"] == pytest.approx(
        float(ind.loc[trade0["exit_date"], "close"]) * (1 - SLIPPAGE), abs=1e-6
    )


def test_update_bayesian_weights_usa_pnl_r_como_fuerza_de_evidencia():
    # T1.6: _update_bayesian_weights pasa pnl_r (retorno en unidades de riesgo)
    # como strength del update Bayesiano, no solo el signo binario.
    # Posición de 10 acciones a 100 en régimen 0 (stop 5%): riesgo = 100*10*0.05 = 50.
    # pnl = +250 = +5R -> strength = 5 -> alpha = prior(1) + 5 = 6.
    engine = BacktestEngine()
    pos = {
        "factors": {"momentum": 0.9, "rsi": 0.9},
        "regime_state": 0,
        "entry_price": 100.0,
        "shares": 10,
    }
    engine._update_bayesian_weights(pos, pnl=250.0)
    alpha, beta = engine.bayesian_updater.get_posterior("0_momentum")
    assert alpha == pytest.approx(6.0)
    assert beta == pytest.approx(1.0)


def test_update_bayesian_weights_pnl_r_pequeno_no_reduce_evidencia():
    # Un outcome de 0.2R (positivo) sigue contando como 1 observación (piso 1.0),
    # nunca menos que el comportamiento binario previo.
    engine = BacktestEngine()
    pos = {
        "factors": {"momentum": 0.9},
        "regime_state": 0,
        "entry_price": 100.0,
        "shares": 10,
    }
    engine._update_bayesian_weights(pos, pnl=10.0)  # 10/50 = 0.2R
    alpha, beta = engine.bayesian_updater.get_posterior("0_momentum")
    assert alpha == pytest.approx(2.0)
    assert beta == pytest.approx(1.0)


def test_update_bayesian_weights_sin_datos_de_riesgo_cae_a_signo():
    # Sin entry_price/shares no hay riesgo en dólares -> fallback a signo binario.
    engine = BacktestEngine()
    pos = {"factors": {"momentum": 0.9}, "regime_state": 0}
    engine._update_bayesian_weights(pos, pnl=5.0)
    alpha, beta = engine.bayesian_updater.get_posterior("0_momentum")
    assert alpha == pytest.approx(2.0)
    assert beta == pytest.approx(1.0)


# ── Tests F0.1 — bootstrap Monte Carlo reproducible (AUDITORIA_NIVEL_DIOS_20260902) ──

class TestMonteCarloBootstrapReproducible:
    """El bootstrap de `monte_carlo_simulation` debe ser determinístico con
    el mismo seed (mismo patrón que `circular_block_bootstrap_ci` T2.2 en
    probabilistic_engine.py:754). Antes del fix usaba `np.random.choice` que
    dependía del global state — no reproducible entre corridas."""

    def _make_trades(self, n=60):
        rng = np.random.default_rng(0)
        pnls = rng.normal(50, 200, n).tolist()
        return [{"pnl": float(p)} for p in pnls]

    def test_mismo_seed_mismo_resultado(self):
        """Determinismo: dos llamadas con mismo seed dan mismo mean/p5/p95."""
        bt = BacktestEngine()
        trades = self._make_trades()
        r1 = bt.monte_carlo_simulation(trades, n_sims=500, seed=42)["bootstrap"]
        r2 = bt.monte_carlo_simulation(trades, n_sims=500, seed=42)["bootstrap"]
        assert r1["mean"] == r2["mean"]
        assert r1["p5"] == r2["p5"]
        assert r1["p95"] == r2["p95"]
        assert r1["prob_loss"] == r2["prob_loss"]

    def test_seed_distinto_resultado_distinto(self):
        """Sanity: cambiar el seed produce distribuciones distintas."""
        bt = BacktestEngine()
        trades = self._make_trades()
        r1 = bt.monte_carlo_simulation(trades, n_sims=500, seed=42)["bootstrap"]
        r3 = bt.monte_carlo_simulation(trades, n_sims=500, seed=99)["bootstrap"]
        assert r1["mean"] != r3["mean"] or r1["p5"] != r3["p5"]

    def test_seed_default_42_presente_en_respuesta(self):
        """El seed usado debe quedar explícito en la respuesta para auditoría."""
        bt = BacktestEngine()
        trades = self._make_trades()
        r = bt.monte_carlo_simulation(trades, n_sims=100, seed=42)["bootstrap"]
        assert r["seed"] == 42

    def test_seed_none_no_determinista_pero_registrado(self):
        """`seed=None` produce resultados no deterministas, pero el campo
        `seed` en la respuesta documenta que fue None (auditoría)."""
        bt = BacktestEngine()
        trades = self._make_trades()
        r1 = bt.monte_carlo_simulation(trades, n_sims=100, seed=None)["bootstrap"]
        r2 = bt.monte_carlo_simulation(trades, n_sims=100, seed=None)["bootstrap"]
        assert r1["seed"] is None
        assert r2["seed"] is None
        # No determinismo — pero al menos uno de los cuantiles debe diferir
        # (probabilidad de colisión exacta en 100 simulaciones ≈ 0)
        assert r1["mean"] != r2["mean"] or r1["p5"] != r2["p5"]

    def test_estructura_respuesta_intacta(self):
        """Las 5 claves (mean, p5, p95, prob_loss, seed) están presentes."""
        bt = BacktestEngine()
        trades = self._make_trades()
        r = bt.monte_carlo_simulation(trades, n_sims=100, seed=42)["bootstrap"]
        for key in ("mean", "p5", "p95", "prob_loss", "seed"):
            assert key in r, f"falta clave {key}"

    def test_sin_trades_bootstrap_vacio(self):
        """Si no hay trades, bootstrap queda {} sin crashear (compat)."""
        bt = BacktestEngine()
        r = bt.monte_carlo_simulation([], n_sims=100, seed=42)
        assert r["bootstrap"] == {}
