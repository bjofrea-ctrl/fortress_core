import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True, scope="session")
def _config_registry_tmp_db(tmp_path_factory):
    """Aísla el ConfigRegistry (T1.5) de la DB de producción: durante TODA
    la suite, el singleton de adaptive_risk apunta a una DB temporal en vez
    de backend/fortress.db. Sin esto, cualquier test que corra un backtest
    sembraría/leería config_history en la DB real."""
    from app.core import adaptive_risk
    from app.core.config_registry import ConfigRegistry

    adaptive_risk._REGISTRY = ConfigRegistry(str(tmp_path_factory.mktemp("config_registry") / "history.db"))
    return adaptive_risk._REGISTRY


@pytest.fixture(autouse=True, scope="session")
def _gate_trial_escape_during_full_suite():
    """A7 (PLAN_REMEDIO_BRECHAS_20260903 §A7): el gate arranca el 2026-09-02.
    La suite completa de tests corre "hoy" (>= 2026-09-04), por lo que
    cualquier test que use `date.today()` cae dentro de la ventana del
    gate — esos tests prueban MECÁNICA del ledger, no la regla del gate.
    Activamos el escape documentado a nivel de sesión para que la suite
    entera siga probando lo que probaba antes; los tests específicos de
    A7 (test_trial_registry_gate.py) lo desactivan explícitamente
    cuando quieren verificar la regla del gate."""
    import os
    os.environ["FORTRESS_ALLOW_GATE_TRIAL"] = "1"
    yield
    # No borramos: si otro proceso hereda esta env, también se beneficia
    # del escape y los tests siguen pasando. Es explícito en el docstring.


@pytest.fixture
def ohlcv_df():
    """OHLCV sintético con tendencia alcista suave, suficiente para el
    warmup de todos los indicadores (ema200/momentum_12_1 necesitan ~252d)."""
    n = 400
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2022-01-03", periods=n)
    drift = np.linspace(0, 40, n)
    noise = np.cumsum(rng.normal(0, 1, n))
    close = 100 + drift + noise
    close = np.maximum(close, 1.0)  # nunca precio negativo

    high = close + rng.uniform(0.1, 1.5, n)
    low = close - rng.uniform(0.1, 1.5, n)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.uniform(1_000_000, 5_000_000, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def short_ohlcv_df(ohlcv_df):
    """Menos de 200 días — el caso que causaba el IndexError histórico."""
    return ohlcv_df.iloc[:50]
