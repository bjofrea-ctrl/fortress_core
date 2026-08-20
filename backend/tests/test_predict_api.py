"""Tests de integración del router /api/predict.

PredictiveEngine.analyze se stubea (nunca NIM, nunca red). Se cubren:
universe (ranking), macro-correlations (prices + regime), analyze/{symbol}
(contrato completo de serialización) y _assess_risk_regime (branching puro).
"""
import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from app.api.routes import predict
from app.core.predictive_engine import PredictiveEngine


def _fake_result():
    cons = SimpleNamespace(bull_score=0.5, bear_score=-0.2, contrarian_score=0.1)
    return SimpleNamespace(
        symbol="TESTA", timestamp="2024-01-02T00:00:00",
        regime_state=0, regime_name="GOLDILOCKS",
        technical_score=0.3, fundamental_score=0.1, macro_score=0.2,
        sentiment_score=0.0, volatility_score=0.1, composite_score=0.55,
        decision="COMPRAR", confidence=0.7,
        prob_up_short=0.6, prob_up_medium=0.55, prob_up_long=0.52,
        manipulation_risk=0.05, manipulation_signals=[],
        triad_score=0.4, triad_recommendation="COMPRAR", triad_agreement="ALTO",
        triad_consensus=cons,
        signals=[
            SimpleNamespace(name="rsi14", category="momentum", value=58.0,
                            signal=1.0, weight=0.2, explanation="RSI sano")
        ],
    )


def _macro_df(n=250, seed=42):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    return pd.DataFrame({"close": close},
                        index=pd.bdate_range("2023-01-02", periods=n))


def _patch_engine(monkeypatch, result):
    monkeypatch.setattr(PredictiveEngine, "analyze", lambda self, **kw: result)
    monkeypatch.setattr(PredictiveEngine, "analyze_macro_correlations",
                        lambda self, macro_data: {"dxy_gold": -0.6})


def _patch_io(monkeypatch, result=None, macro=None, cache_dir=None):
    monkeypatch.setattr(predict, "download_data",
                        lambda symbol, start="2015-01-01": _macro_df())
    monkeypatch.setattr(predict, "_load_macro_data", lambda: macro or {})
    monkeypatch.setattr(predict, "_load_sentiment_data", lambda: None)
    monkeypatch.setattr(predict, "get_fundamentals_api", lambda symbol: None)
    if cache_dir is not None:
        monkeypatch.setattr(predict, "CACHE_DIR", cache_dir)
    if result is not None:
        _patch_engine(monkeypatch, result)


def test_analyze_contrato_completo(monkeypatch, ohlcv_df):
    result = _fake_result()
    _patch_io(monkeypatch, result=result)
    monkeypatch.setattr(predict, "download_data", lambda s, start=None: ohlcv_df)

    body = asyncio.run(predict.analyze_symbol("TESTA"))
    assert body["symbol"] == "TESTA"
    assert body["composite_score"] == 0.55
    assert body["decision"] == "COMPRAR"
    assert body["triad_bull"] == 0.5
    assert body["fundamentals_source"] == "unavailable"
    assert body["signals"][0]["name"] == "rsi14"
    assert "COMPRAR" in body["recommendation_text"]


def test_analyze_degradado_sin_datos(monkeypatch):
    _patch_io(monkeypatch, result=None)
    monkeypatch.setattr(predict, "download_data",
                        lambda s, start=None: pd.DataFrame())
    with pytest.raises(Exception):
        asyncio.run(predict.analyze_symbol("TESTA"))


def test_universe_rankea_y_skip_series_cortas(monkeypatch, tmp_path):
    df_long = _macro_df()
    monkeypatch.setattr(predict, "CACHE_DIR", str(tmp_path))
    pd.DataFrame({"close": [1.0]}).to_parquet(str(tmp_path / "CORTO.parquet"))
    _macro_df().to_parquet(str(tmp_path / "LARGO.parquet"))

    monkeypatch.setattr(predict, "SYMBOLS", ["CORTO", "LARGO"])
    _patch_io(monkeypatch, result=_fake_result())
    # el download de CORTOS dura 1 fila -> el universo lo saltea
    monkeypatch.setattr(predict, "download_data",
                        lambda symbol, start="2015-01-01": df_long if symbol != "CORTO" else df_long.iloc[:50])

    body = asyncio.run(predict.analyze_universe(regime_state=1))
    assert body["regime_state"] == 1
    assert body["count"] == 1
    assert body["symbols"][0]["symbol"] == "TESTA"
    assert set(body["symbols"][0]) >= {"symbol", "decision", "composite_score",
                                       "prob_up_short", "manipulation_risk"}


def test_macro_correlations_estructura(monkeypatch):
    macro = {name: _macro_df(seed=i) for i, name in
             enumerate(["DXY", "gold", "silver", "SPY", "copper", "oil", "TLT"])}
    _patch_io(monkeypatch, macro=macro)
    _patch_engine(monkeypatch, _fake_result())

    body = asyncio.run(predict.get_macro_correlations())
    assert "prices" in body and "correlations" in body and "risk_regime" in body
    assert body["correlations"]["dxy_gold"] == -0.6
    p = body["prices"]
    assert len(p) == 7
    assert all(k in next(iter(p.values())) for k in ["price", "return_20d_pct", "return_90d_pct"])


def test_assess_risk_regime_risk_on(monkeypatch):
    dxy = _macro_df(n=250)
    dxy["close"] = 100 * np.linspace(1.0, 0.85, 250)  # DXY -15% en 250d -> 20d < -1%
    gold = _macro_df(n=250)
    gold["close"] = 100 * np.linspace(1.0, 1.15, 250)  # oro +15%
    silver = _macro_df(n=250)
    silver["close"] = 100 * np.linspace(1.0, 1.30, 250)  # silver/gold < 65
    spy = _macro_df(n=250)
    spy["close"] = 100 * np.linspace(1.0, 1.10, 250)  # S&P +10% en 250d
    copper = _macro_df(n=250)
    copper["close"] = 100 * np.linspace(1.0, 1.05, 250)  # sobre MA200

    assessment = predict._assess_risk_regime(
        {"DXY": dxy, "gold": gold, "silver": silver, "SPY": spy, "copper": copper})
    assert assessment["regime"] in ("RISK_ON", "RISK_ON_FUERTE")
    assert assessment["score"] >= 0.5
    assert any("Risk-ON" in s for s in assessment["signals"])


def test_assess_risk_regime_neutral_sin_datos():
    assessment = predict._assess_risk_regime({})
    assert assessment["regime"] == "NEUTRAL"
    assert assessment["score"] == 0.0
    assert assessment["signals"] == []
