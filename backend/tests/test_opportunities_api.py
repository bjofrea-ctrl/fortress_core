"""Tests del contrato del endpoint /api/opportunities/today.

El endpoint se prueba con datos sintéticos (monkeypatch de las cargas) para
validar la ESTRUCTURA de la respuesta sin depender de red ni de ~60s de
cálculo: header con régimen, candidatos con razón completa, plan de salida,
concentración de cola y track record.

Nota: se llama a la corutina del router directamente (asyncio.run) — el repo
no tiene httpx/TestClient en dev-deps; esto valida el mismo contrato.
"""
import asyncio

import numpy as np
import pandas as pd
import pytest

from app.api.routes import opportunities as opp
from app.core import suggestions_store as store


@pytest.fixture
def bullish_data() -> dict:
    """3 símbolos con tendencia fuerte y volumen creciente: pasan el gate
    completo (trend_ok, adx>=20, 40<rsi<75, vol_ratio>=1)."""
    return {s: _bull(s) for s in ["TESTA", "TESTB", "TESTC"]}


def _monkeypatch_io(monkeypatch, price_data, regime=None):
    market = {t: pd.DataFrame({"close": price_data["TESTA"]["close"]}) for t in opp.MARKET_TICKERS}
    monkeypatch.setattr(opp, "_load_market_data", lambda: market)
    monkeypatch.setattr(opp, "_load_price_data", lambda: price_data)
    monkeypatch.setattr(opp, "_load_sentiment_map", lambda trading_dates: {})
    if regime is not None:
        monkeypatch.setattr(opp, "_fit_regime", lambda md: regime)


def _call(monkeypatch, tmp_path, price_data, regime):
    monkeypatch.setattr(store, "SUGGESTIONS_PATH", str(tmp_path / "s.json"))
    _monkeypatch_io(monkeypatch, price_data, regime)
    return asyncio.run(opp.opportunities_today())


def test_today_returns_opportunities_with_full_reason(monkeypatch, tmp_path):
    body = _call(
        monkeypatch, tmp_path, {s: _bull(s) for s in ["TESTA", "TESTB", "TESTC"]},
        regime={"state": 1, "state_name": "REFLATION", "confidence": 0.8},
    )

    assert body["regime"]["state"] == 1
    assert body["regime"]["name"] == "REFLATION"
    assert body["blocked_reason"] is None

    assert len(body["opportunities"]) >= 1
    o = body["opportunities"][0]
    for key in ["symbol", "score", "win_prob", "factors", "gates", "entry_price",
                "stop_loss", "take_profit", "payoff_ratio", "atr", "exit_plan"]:
        assert key in o, f"falta {key}"
    assert o["exit_plan"]["partial_tp"]["trigger"] == "precio >= entrada + 2*ATR"
    assert "%" in o["exit_plan"]["regime_stop"]["trigger"]
    assert o["exit_plan"]["regime_stop"]["action"] == "cerrar la posición (stop de régimen)"


def test_today_blocked_on_regime_3(monkeypatch, tmp_path):
    body = _call(
        monkeypatch, tmp_path, {s: _bull(s) for s in ["TESTA", "TESTB", "TESTC"]},
        regime={"state": 3, "state_name": "DEFLATION", "confidence": 0.95},
    )

    assert body["regime"]["state"] == 3
    assert body["blocked_reason"] is not None, "régimen 3 se explica, no lista vacía muda"
    assert body["opportunities"] == []
    assert body["concentration"]["alerts"] == []


def test_today_tracks_concentration(monkeypatch, tmp_path):
    data = {s: _bull(s) for s in ["TESTA", "TESTB", "TESTC"]}
    body = _call(
        monkeypatch, tmp_path, data,
        regime={"state": 1, "state_name": "REFLATION", "confidence": 0.8},
    )

    assert len(body["opportunities"]) == 3
    assert body["concentration"]["n_pairs_analyzed"] == 3
    syms = [o["symbol"] for o in body["opportunities"]]
    assert syms == sorted(syms), "todos comparten la misma tendencia -> ya ordenado por score"


def _bull(sym: str) -> pd.DataFrame:
    """Serie determinista con tendencia fuerte y pullbacks realistas:
    patrón 11 días +0.8% / 3 días -1.5% -> RSI Wilder ~66 (40-75),
    ADX alto, close siempre > ema50 > ema200. Gate completo aprobado."""
    n = 400
    dates = pd.bdate_range("2024-01-02", periods=n)
    rets = np.array([0.008 if i % 14 < 11 else -0.015 for i in range(n)])
    close = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": 2_000_000 * np.linspace(1.0, 2.2, n),
        },
        index=dates,
    )
