"""Tests de T1.5 — registro de parámetros versionado con reconstrucción
point-in-time (PLAN_INTEGRACION_INDICAGENT.md, líneas 613-703).

Cubre los criterios de aceptación:
1. get_at() reconstruye la versión vigente en un timestamp intermedio, no la
   más reciente.
2. Un backtest sobre 2023 NO cambia sus resultados después de set() sobre el
   stop del régimen que opera en ese período (get_at reconstruye 2023, no el
   valor actual) — y además se prueba la materialidad: si el ajuste hubiera
   estado vigente en 2023, los resultados SÍ cambiarían.
3. AdaptiveRiskManager.get_thresholds() usa get_regime_thresholds() con el
   date del backtest en curso.
4. pytest de test_config_registry.py + test_risk_manager.py en verde.
"""
import json
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from app.core import adaptive_risk
from app.core.adaptive_risk import AdaptiveRiskManager
from app.core.backtest_engine import BacktestEngine
from app.core.config_registry import INITIAL_ESTIMATE, ConfigRegistry

_MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]


@pytest.fixture
def registry(tmp_path):
    return ConfigRegistry(str(tmp_path / "history.db"))


# ---------- Criterio 1: reconstrucción point-in-time del registro ----------


def test_get_at_reconstruye_la_version_vigente_en_timestamp_intermedio(registry):
    registry.set(
        "strategy.risk_stop", 0.05, "initial_estimate", "v1",
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    registry.set(
        "strategy.risk_stop", 0.10, "tuner", "v2",
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # timestamp intermedio entre las dos versiones -> la vigente entonces (0.05)
    assert registry.get_at("strategy.risk_stop", datetime(2023, 6, 1, tzinfo=timezone.utc)) == 0.05
    # después de la v2 -> la más reciente (0.10)
    assert registry.get_at("strategy.risk_stop", datetime(2024, 6, 1, tzinfo=timezone.utc)) == 0.10
    # antes de cualquier versión -> default
    assert registry.get_at("strategy.risk_stop", datetime(2019, 1, 1, tzinfo=timezone.utc)) is None
    # get() (vigente HOY) -> la más reciente
    assert registry.get("strategy.risk_stop") == 0.10


def test_get_at_acepta_timestamps_naive_como_utc(registry):
    registry.set(
        "strategy.risk_stop", 0.05, "initial_estimate", "v1",
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    registry.set(
        "strategy.risk_stop", 0.10, "tuner", "v2",
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    # pd.Timestamp / datetime naive (como las fechas del loop de backtest)
    assert registry.get_at("strategy.risk_stop", pd.Timestamp("2023-06-01")) == 0.05
    assert registry.get_at("strategy.risk_stop", datetime(2024, 6, 1)) == 0.10


def test_set_serializa_valores_json(registry):
    registry.set("strategy.params", {"a": [1, 2], "b": True}, "x", "r")
    assert registry.get("strategy.params") == {"a": [1, 2], "b": True}


def test_set_es_append_only_nunca_update(registry):
    registry.set("k", "a", "x", "r1")
    registry.set("k", "b", "x", "r2")
    with sqlite3.connect(registry.db_path) as conn:
        rows = conn.execute(
            "SELECT value, version FROM config_history WHERE key = 'k' ORDER BY version"
        ).fetchall()
    assert [json.loads(v) for v, _ in rows] == ["a", "b"]
    assert [v for _, v in rows] == [1, 2]


# ---------- Seed inicial de REGIME_THRESHOLDS ----------


def test_seed_inicial_carga_regime_thresholds_como_initial_estimate(registry):
    with sqlite3.connect(registry.db_path) as conn:
        rows = conn.execute(
            "SELECT key, value, version, changed_by, reason FROM config_history"
            " WHERE changed_by = ? ORDER BY key",
            (INITIAL_ESTIMATE,),
        ).fetchall()
    # 4 regímenes x 4 campos = 16 claves, todas versión 1 con provenance semilla
    assert len(rows) == 16
    by_key = {r[0]: r for r in rows}
    assert by_key["risk.regime.0.position_stop"][1] == json.dumps(0.05)
    assert by_key["risk.regime.0.position_stop"][2] == 1
    assert by_key["risk.regime.2.cooldown_days"][1] == json.dumps(10)
    assert by_key["risk.regime.3.max_exposure"][1] == json.dumps(0.20)


def test_seed_es_idempotente_sin_duplicar_versiones(registry):
    ConfigRegistry(registry.db_path)  # reinstanciar: no debe re-insertar seeds
    with sqlite3.connect(registry.db_path) as conn:
        assert conn.execute(
            "SELECT version FROM config_history WHERE key = 'risk.regime.0.position_stop'"
        ).fetchall() == [(1,)]


def test_get_devuelve_el_seed_sin_ajustes(registry):
    assert registry.get("risk.regime.0.position_stop") == 0.05
    assert registry.get("risk.regime.2.cooldown_days") == 10


# ---------- Criterio 3: get_thresholds lee del registro con la fecha del backtest ----------


def test_get_thresholds_usa_la_fecha_del_backtest_en_curso(monkeypatch, tmp_path):
    registry = ConfigRegistry(str(tmp_path / "risk.db"))
    registry.set(
        "risk.regime.0.position_stop", 0.50, "tuner", "ajuste posterior a 2023",
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(adaptive_risk, "_REGISTRY", registry)

    rm = AdaptiveRiskManager(initial_equity=25000)
    rm.update_regime(0)

    rm.state.current_date = datetime(2023, 6, 1)  # backtest sobre 2023
    assert rm.get_thresholds()["position_stop"] == 0.05  # seed, no el ajuste

    rm.state.current_date = datetime(2024, 6, 1)  # backtest que ya alcanza el ajuste
    assert rm.get_thresholds()["position_stop"] == 0.50


def test_check_all_stops_registra_la_fecha_del_backtest(monkeypatch, tmp_path):
    monkeypatch.setattr(adaptive_risk, "_REGISTRY", ConfigRegistry(str(tmp_path / "risk.db")))
    rm = AdaptiveRiskManager(initial_equity=25000)
    rm.update_regime(0)
    date = datetime(2023, 6, 1)
    rm.check_all_stops(25000, {}, {}, date)
    assert rm.state.current_date == date


# ---------- Criterio 2: backtest 2023 inalterado por un ajuste futuro ----------


def _build_2023_panel(n=1350, drift=0.0008, sd=0.005, seed=42, floor=-0.02):
    """Panel sintético determinístico (mismo seed que el HMM random_state=42):
    tendencia suave + ruido pequeño, calibrado para que generate_signal opere
    varias veces durante 2023 en régimen 2 (verificado empíricamente)."""
    dates = pd.bdate_range("2019-01-01", periods=n)
    rng = np.random.default_rng(seed)
    rets = drift + rng.normal(0, sd, n)
    price = 100 * np.cumprod(1 + np.maximum(rets, floor))
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


class _RecordingRiskManager(AdaptiveRiskManager):
    """Subclase transparente que captura los umbrales que el backtest realmente usa."""

    def __init__(self, initial_equity, capture):
        super().__init__(initial_equity)
        self._capture = capture

    def get_thresholds(self, at_date=None):
        th = super().get_thresholds(at_date=at_date)
        self._capture.append(
            {"regime": self.state.current_regime, "position_stop": th["position_stop"]}
        )
        return th


class _RecordingEngine(BacktestEngine):
    def __init__(self, capture, **kwargs):
        super().__init__(**kwargs)
        self._capture = capture

    def _make_risk_manager(self):
        return _RecordingRiskManager(self.initial_capital, self._capture)


def test_backtest_2023_inalterado_por_ajuste_futuro(monkeypatch, tmp_path):
    registry = ConfigRegistry(str(tmp_path / "backtest.db"))
    monkeypatch.setattr(adaptive_risk, "_REGISTRY", registry)

    panel = _build_2023_panel()
    market = {t: panel.copy() for t in _MARKET_TICKERS}
    start, end = pd.Timestamp("2023-01-02"), pd.Timestamp("2023-12-31")

    capture_before = []
    res_before = _RecordingEngine(capture_before, initial_capital=25000).run(
        {"SYN": panel}, market, start, end
    )
    assert res_before["metrics"]["total_trades"] > 0, "el panel sintético debe operar en 2023"

    # Ajuste FUTURO (2024) del stop del régimen que opera en este backtest (2).
    # Si get_thresholds leyera el valor vigente HOY, contaminaría el 2023.
    registry.set(
        "risk.regime.2.position_stop", 0.50, "tuner", "ajuste posterior a 2023",
        valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    capture_after = []
    res_after = _RecordingEngine(capture_after, initial_capital=25000).run(
        {"SYN": panel}, market, start, end
    )

    # (a) resultados del MISMO backtest 2023: idénticos
    assert res_after["metrics"] == res_before["metrics"]
    assert res_after["trades"] == res_before["trades"]

    # (b) el umbral reconstruido para 2023 es el seed (0.08 en régimen 2),
    # jamás el valor ajustado (0.50)
    assert capture_before and capture_after
    assert all(c["position_stop"] != 0.50 for c in capture_before)
    assert all(c["position_stop"] != 0.50 for c in capture_after)
    regime2_after = [c for c in capture_after if c["regime"] == 2]
    assert regime2_after and all(c["position_stop"] == 0.08 for c in regime2_after)

    # (c) el registro SÍ tiene el valor nuevo vigente para el presente — el
    # punto-in-time es lo que bloquea la contaminación, no un set() fallido
    assert registry.get("risk.regime.2.position_stop") == 0.50
    assert registry.get_at("risk.regime.2.position_stop", datetime(2024, 6, 1, tzinfo=timezone.utc)) == 0.50
    assert registry.get_at("risk.regime.2.position_stop", datetime(2023, 6, 1, tzinfo=timezone.utc)) != 0.50

    # (d) materialidad: si el mismo ajuste hubiera estado vigente en 2023
    # (valid_from=2020), los resultados del backtest SÍ cambiarían
    alt_registry = ConfigRegistry(str(tmp_path / "alt.db"))
    alt_registry.set(
        "risk.regime.2.position_stop", 0.50, "tuner", "ajuste vigente en 2023",
        valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(adaptive_risk, "_REGISTRY", alt_registry)
    res_alt = _RecordingEngine([], initial_capital=25000).run({"SYN": panel}, market, start, end)
    assert res_alt["metrics"] != res_before["metrics"]
