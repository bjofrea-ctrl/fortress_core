"""Tests de T0.2 — ejecución con lag (PLAN_INTEGRACION_INDICAGENT.md).

El motor end-of-day calcula la señal con el cierre de 'date' pero, con
execution_lag_days=1 (default nuevo), ejecuta en la APERTURA de la barra
siguiente ('date+1'). execution_lag_days=0 conserva el comportamiento ANTERIOR
(el bug): señal y ejecución comparten la misma barra (cierre de 'date').

Estos tests arman un panel sintético determinístico que dispara UNA señal un
lunes conocido, le inyectan un gap overnight grande y verificado en el martes,
y comprueban que el precio de entrada registrado es la apertura del día
siguiente y NO el cierre del día de la señal.

REGIMEN: estos tests verifican la MECÁNICA de ejecución con lag, no la
clasificación de régimen. El market_data sintético usa el MISMO dataframe para
los 9 tickers (features de retorno idénticas), así que el régimen HMM estimado
sobre ese panel degenerado es arbitrario y puede reetiquetarse al cambiar el
alineamiento semántico (FIX B6, MAPEO_ESTADOS_HMM.md): con VIX ascendente el
día de la señal cae en DEFLATION y el gate de elegibilidad (regime_state==3 en
signal_engine) lo bloquea — comportamiento CORRECTO del motor, irrelevante
para la mecánica de lag que estos tests prueban. Por eso `_run` fija la
entrada de régimen del motor a GOLDILOCKS (0). NO se tocan signal_engine ni el
criterio de elegibilidad: solo se controla la entrada que el motor observa.
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
    """Corre el backtest sobre el panel sintético.

    Fija la entrada de régimen del motor a GOLDILOCKS (0) parcheando
    ``regime_classifier.predict_current_regime`` — ver nota REGIMEN arriba.
    El fit HMM real sigue corriendo (camino de integración intacto); solo se
    controla el estado semántico que el motor observa para aislar la mecánica
    de ejecución con lag que estos tests verifican.
    """
    engine = BacktestEngine(initial_capital=25000)
    clf = engine.regime_classifier

    def _fixed_regime(*args, **kwargs):
        return {
            "state": 0,
            "state_name": clf.state_labels[0],
            "allocation": clf.REGIME_ALLOCATION[0],
            "confidence": 1.0,
        }

    clf.predict_current_regime = _fixed_regime
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


# =====================================================================
# A6 (PLAN_REMEDIO_BRECHAS_20260903 §A6) — n_trials del motor = ledger
# =====================================================================
#
# El default de calculate_metrics() antes era DEFAULT_N_TRIALS = 5 (número
# mágico de las 5 variantes que se probaron en la sesión original). Eso
# sub-deflacionaba el DSR desde el momento en que la familia signal_diagnosis
# superó 5. A6 corrige el bug: el default ahora se resuelve del ledger vía
# trial_registry.consumed_budget('signal_diagnosis') (29 al cierre del plan).
#
# Los callers explícitos (validacion_oos_fresca_mom_rsi.py, trial_evt_stops*.py)
# NO cambian: pasan su n_trials y eso es lo correcto para su contexto.


def _equity_curve_borderline(n=1500, seed=11):
    """Serie sintética con Sharpe moderado (cerca del threshold Bailey-Lopez)
    para que el DSR discrimine bien entre n=5 y n=29 — necesario para
    verificar que la corrección deflaciona de verdad y no es cosmética."""
    import datetime as _dt
    rng = np.random.default_rng(seed)
    ret = 0.0002
    vol = 0.015
    eq = []
    price = 25000.0
    start = _dt.date(2020, 1, 1)
    for i in range(n):
        d = start + _dt.timedelta(days=int(i * 1.4))
        price *= np.exp(ret - 0.5 * vol * vol + vol * rng.normal())
        dd = max(0.0, (1 - price / 26000) * 6)
        eq.append({"date": d, "equity": price, "drawdown_pct": -dd})
    return eq


def _trades_borderline(n=150, seed=11):
    rng = np.random.default_rng(seed + 1)
    return [{"pnl": float(rng.normal(20, 180))} for _ in range(n)]


class TestA6NtrialsFromLedger:
    """A6: el default de calculate_metrics() lee del ledger."""

    def test_default_n_trials_constante_es_None(self):
        """Invariante de contrato: DEFAULT_N_TRIALS ya no es 5."""
        assert BacktestEngine.DEFAULT_N_TRIALS is None

    def test_calculate_metrics_signature_acepta_None_explicito(self):
        """El type hint debe ser Optional[int], no int (callers pueden pasar None)."""
        import inspect
        import typing
        sig = inspect.signature(BacktestEngine.calculate_metrics)
        ann = sig.parameters["n_trials"].annotation
        # En Python 3.9 (target del repo) el annotation puede ser la clase
        # o el string. Aceptamos ambas formas siempre que diga Optional[int].
        assert ann in ("Optional[int]", typing.Optional[int]), (
            f"annotation inesperada: {ann!r}"
        )
        assert sig.parameters["n_trials"].default is None

    def test_calculate_metrics_sin_n_trials_usa_ledger_actual(self, monkeypatch):
        """Sin pasar n_trials, el resultado usa el n del ledger vivo (>= 1)."""
        from app.core import trial_registry as tr
        monkeypatch.setattr(tr, "consumed_budget", lambda fam, path=None, today=None: 17)
        eng = BacktestEngine()
        m = eng.calculate_metrics(_equity_curve_borderline(), _trades_borderline())
        assert m["deflated_sharpe_n_trials"] == 17
        assert m["n_trials_source"] == "ledger"
        assert m["n_trials_fallback_reason"] is None

    def test_calculate_metrics_respeta_n_trials_explicito(self, monkeypatch):
        """Si paso n_trials=10, usa 10 — los callers explícitos no cambian."""
        from app.core import trial_registry as tr
        # Aunque el ledger diga 17, el caller manda.
        monkeypatch.setattr(tr, "consumed_budget", lambda fam, path=None, today=None: 17)
        eng = BacktestEngine()
        m = eng.calculate_metrics(
            _equity_curve_borderline(), _trades_borderline(), n_trials=10
        )
        assert m["deflated_sharpe_n_trials"] == 10
        assert m["n_trials_source"] == "explicit"
        assert m["n_trials_fallback_reason"] is None

    def test_calculate_metrics_dsr_mas_conservador_con_n_mayor(self, monkeypatch):
        """El DSR con N=29 es <= al DSR con N=5 (sentido del fix: deflaciona)."""
        from app.core import trial_registry as tr
        monkeypatch.setattr(tr, "consumed_budget", lambda fam, path=None, today=None: 29)
        eng = BacktestEngine()
        m5 = eng.calculate_metrics(
            _equity_curve_borderline(seed=11), _trades_borderline(seed=11), n_trials=5
        )
        m29 = eng.calculate_metrics(
            _equity_curve_borderline(seed=11), _trades_borderline(seed=11), n_trials=29
        )
        # Sentido: a mayor n_trials, mayor SR_0, menor DSR (con misma muestra).
        assert m29["deflated_sharpe"] <= m5["deflated_sharpe"] + 1e-9
        # Y la diferencia es no-trivial — verifica que el cambio no es cosmético.
        assert (m5["deflated_sharpe"] - m29["deflated_sharpe"]) > 0.05

    def test_calculate_metrics_fallback_cuando_ledger_falla(self, monkeypatch):
        """Si consumed_budget del ledger no está disponible, usa fallback
        conservador (29) y deja la razón escrita en el payload."""
        from app.core import trial_registry as tr
        def _broken(*a, **kw):
            raise RuntimeError("ledger corrupto de prueba")
        monkeypatch.setattr(tr, "consumed_budget", _broken)
        eng = BacktestEngine()
        m = eng.calculate_metrics(_equity_curve_borderline(), _trades_borderline())
        assert m["deflated_sharpe_n_trials"] == 29  # fallback conservador
        assert m["n_trials_source"] == "ledger"
        assert m["n_trials_fallback_reason"] is not None
        assert "RuntimeError" in m["n_trials_fallback_reason"]
        assert "ledger corrupto" in m["n_trials_fallback_reason"]

    def test_calculate_metrics_fallback_cuando_ledger_devuelve_cero(self, monkeypatch):
        """Si consumed_budget devuelve 0 (estado patológico), fallback."""
        from app.core import trial_registry as tr
        monkeypatch.setattr(tr, "consumed_budget", lambda fam, path=None, today=None: 0)
        eng = BacktestEngine()
        m = eng.calculate_metrics(_equity_curve_borderline(), _trades_borderline())
        assert m["deflated_sharpe_n_trials"] == 29
        assert m["n_trials_fallback_reason"] is not None

    def test_calculate_metrics_fallback_cuando_ledger_devuelve_no_entero(self, monkeypatch):
        """Si consumed_budget devuelve un valor no-entero, fallback."""
        from app.core import trial_registry as tr
        monkeypatch.setattr(tr, "consumed_budget", lambda fam, path=None, today=None: "17")
        eng = BacktestEngine()
        m = eng.calculate_metrics(_equity_curve_borderline(), _trades_borderline())
        assert m["deflated_sharpe_n_trials"] == 29
        assert m["n_trials_fallback_reason"] is not None

    def test_resolve_default_n_trials_sobre_senal_viva(self):
        """Sin monkeypatch, el resolver lee el ledger real (>= 1; en este
        worktree es 29 al cierre del plan, pero se permite >= 1 para no
        atar el test al conteo exacto que puede cambiar)."""
        n, reason = BacktestEngine()._resolve_default_n_trials()
        assert isinstance(n, int) and n >= 1
        assert reason is None

    def test_calculate_metrics_paylod_incluye_trazabilidad_A6(self):
        """Las 3 claves nuevas del payload existen (contrato API)."""
        m = BacktestEngine().calculate_metrics(
            _equity_curve_borderline(), _trades_borderline(), n_trials=5
        )
        for key in ("deflated_sharpe_n_trials", "n_trials_source", "n_trials_fallback_reason"):
            assert key in m, f"falta clave A6: {key}"
        # Caller explícito → source=explicit, fallback_reason=None
        assert m["n_trials_source"] == "explicit"
        assert m["n_trials_fallback_reason"] is None
