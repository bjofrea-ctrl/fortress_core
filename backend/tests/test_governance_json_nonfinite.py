"""
Regresión del 500 por floats no-finitos en /api/governance/analyze/{symbol}.

Causa raíz (production log): Starlette serializa la respuesta con
json.dumps(..., allow_nan=False) (starlette/responses.py:183). Un único float
NaN/±Inf en el payload —originado por la cache corrupta de SPY: barra
2026-09-08=-76.8% y fila 2026-09-09 toda NaN— levanta
`ValueError: Out of range float values are not JSON compliant` DURANTE EL RENDER,
fuera del try/except del handler. Resultado: 500 ASGI crudo, sin detail, que el
`except Exception` jamás ve. Por eso "nunca se diagnosticó".

Capa 1 del fix: `_json_safe()` coacciona no-finitos a None antes de retornar.
Estos tests (1) replican la falla cruda, (2) prueban que el handler sanea sobre el
MISMO render que crashaba, (3) unidad de `_json_safe`. Hermético: monkeypatchea
download_data/_load_macro_data/get_fundamentals_api/PredictiveEngine.analyze/
GovernanceSystem.process_governance (sin red, sin NIM).
"""
import asyncio
import math
from types import SimpleNamespace

import numpy as np
import pytest
from starlette.responses import JSONResponse

from app.api.routes import governance as gov_route
from app.config import settings
from app.core.advanced_agents import GovernanceSystem
from app.core.predictive_engine import PredictiveEngine


NAN = float("nan")
INF = float("inf")


def _fake_result_nonfinite():
    """PredictiveResult-like con no-finitos reales en el payload (caso SPY)."""
    cons = SimpleNamespace(bull_score=NAN, bear_score=0.4, contrarian_score=INF)
    return SimpleNamespace(
        symbol="SPY", timestamp="2026-09-09T00:00:00",
        regime_state=0, regime_name="GOLDILOCKS",
        technical_score=0.3, fundamental_score=0.1, macro_score=0.2,
        sentiment_score=0.0, volatility_score=0.1,
        composite_score=NAN,
        decision="MANTENER", confidence="Media",
        motor="heuristico_no_validado", probabilidades_calibradas=False,
        prob_up_short=INF, prob_up_medium=0.55, prob_up_long=0.52,
        manipulation_risk=NAN, manipulation_signals=[],
        triad_score=NAN, triad_recommendation="MANTENER", triad_agreement="BAJO",
        triad_consensus=cons, signals=[],
    )


def _stub_governance_process_nonfinite(*args, **kwargs):
    return {
        "triad": {"bull": {"score": NAN, "verdict": "MANTENER"},
                  "bear": {"score": 0.0, "verdict": "MANTENER"},
                  "contrarian": {"score": 0.0, "verdict": "MANTENER"},
                  "consensus": 0.0, "decision": "MANTENER", "agreement": "DESHABILITADO"},
        "controller": {"approved": False, "decision": "MANTENER", "suggested_position": INF},
        "judge": {"verdict": "MANTENER", "overruled_agents": []},
        "brier": NAN,
        "final_decision": "MANTENER",
        "final_reason": "deterministic fallback",
    }


def _patch_io(monkeypatch, ohlcv_df):
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    monkeypatch.setattr(PredictiveEngine, "analyze", lambda self, **kw: _fake_result_nonfinite())
    monkeypatch.setattr(GovernanceSystem, "process_governance", _stub_governance_process_nonfinite)
    monkeypatch.setattr(gov_route, "download_data", lambda s, start=None: ohlcv_df)
    monkeypatch.setattr(gov_route, "_load_macro_data", lambda: {})
    monkeypatch.setattr(gov_route, "get_fundamentals_api", lambda s: None)


# ===== TESTS =====


def test_baseline_payload_con_nan_revienta_el_render():
    """Rojo documentado: sin sanear, JSONResponse(allow_nan=False) NO puede render."""
    sucio = {"a": 1.0, "b": NAN, "nested": {"c": [INF, 2.0]}}
    with pytest.raises(ValueError, match="Out of range float values"):
        JSONResponse(sucio).render()


def test_analyze_governance_no_500_por_nan(monkeypatch, ohlcv_df):
    """Con el fix, /analyze con métricas no-finitas renderiza y las lleva a None."""
    _patch_io(monkeypatch, ohlcv_df)

    body = asyncio.run(gov_route.analyze_with_governance("SPY"))

    # JSONResponse renderiza en __init__ con allow_nan=False (el MISMO path que
    # crashaba en producción). Si quedara un no-finito, esto levantaría ValueError.
    resp = JSONResponse(body)
    assert isinstance(resp.body, (bytes, bytearray)) and len(resp.body) > 0


    # No-finitos coaccionados a None en todos los niveles.
    assert body["predictive"]["composite_score"] is None
    assert body["predictive"]["prob_up_short"] is None
    assert body["predictive"]["prob_up_medium"] == 0.55          # finito intacto
    assert body["predictive"]["prob_up_long"] == 0.52            # finito intacto
    assert body["governance"]["controller"]["suggested_position"] is None
    assert body["governance"]["brier"] is None
    assert body["governance"]["triad"]["bull"]["score"] is None

    # Barrido defensivo: nada no-finito sobrevive en el payload.
    def _assert_no_nonfinite(x):
        if isinstance(x, float):
            assert math.isfinite(x), "float no-finito remanente en el payload"
        elif isinstance(x, dict):
            for v in x.values():
                _assert_no_nonfinite(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                _assert_no_nonfinite(v)
    _assert_no_nonfinite(body)


def test_json_safe_preserva_finitos_y_tipos():
    src = {"i": 3, "f": 0.5, "zero": 0.0, "neg": -1.25, "s": "x",
           "t": True, "n": None, "list": [1, 2.0, "a"]}
    assert gov_route._json_safe(src) == src


def test_json_safe_coacciona_nan_e_inf():
    assert gov_route._json_safe(NAN) is None
    assert gov_route._json_safe(INF) is None
    assert gov_route._json_safe(-INF) is None
    assert gov_route._json_safe({"a": [NAN, {"b": INF}]}) == {"a": [None, {"b": None}]}


def test_json_safe_toma_numpy_float64_nan():
    """np.float64 es subclase de float: debe caer en la rama de float -> None."""
    assert gov_route._json_safe(np.float64("nan")) is None
    assert gov_route._json_safe(np.float64("inf")) is None
    assert gov_route._json_safe(np.float64(2.5)) == 2.5


def test_json_safe_no_mut_booleans():
    """bool NO es float; True/False deben sobrevivir intactos."""
    assert gov_route._json_safe({"ok": True, "bad": False}) == {"ok": True, "bad": False}
