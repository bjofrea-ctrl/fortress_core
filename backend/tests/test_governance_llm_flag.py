"""
Tests de A9 (PLAN_REMEDIO_BRECHAS_20260903 §A9) — flag GOVERNANCE_LLM_ENABLED.

Cubre:
  - La setting existe, default False, modificable.
  - NvidiaNIMClient.generate() respeta la flag (chokepoint único).
  - /api/predict/analyze/{symbol} expone `governance_mode` en el payload.
  - /api/governance/status expone `governance_llm_enabled` y `nvidia_nim_blocked_by_a9`.
  - /api/governance/analyze/{symbol} etiqueta `final_reason` con
    `GOVERNANCE_LLM_DISABLED_BY_A9` cuando la flag está apagada.
  - El motor validado (signal_engine.py) NO consulta la flag (regresión D1).

Diseño: todos los tests son herméticos (sin red, sin NIM real). Los que
tocan la flag usan monkeypatch sobre `settings.GOVERNANCE_LLM_ENABLED`
(pydantic-settings no permite setear en instancia después del init,
así que se monkeypathea el atributo de settings usado por el código).
"""
import asyncio
import inspect
import os
from types import SimpleNamespace
from unittest import mock

from app.api.routes import governance as gov_route
from app.api.routes import predict as pred_route
from app.config import settings
from app.core.advanced_agents import GovernanceSystem, NvidiaNIMClient
from app.core.predictive_engine import PredictiveEngine

# ============================================================ setting


def test_setting_governance_llm_enabled_existe():
    """El setting existe en Settings (config.py)."""
    assert hasattr(settings, "GOVERNANCE_LLM_ENABLED")
    assert isinstance(settings.GOVERNANCE_LLM_ENABLED, bool)


def test_setting_governance_llm_enabled_default_false():
    """Default del gate: False. El plan A9 lo declara explícito."""
    # Si el test corre con la env var seteada de otro test, lo respetamos
    # pero verificamos que el default DE CÓDIGO (no env) es False.
    src = inspect.getsource(__import__("app.config", fromlist=["Settings"]))
    assert "GOVERNANCE_LLM_ENABLED: bool = False" in src


def test_setting_modificable_para_escape_hatch(monkeypatch):
    """El setting es un bool — operador puede activarlo en .env o runtime."""
    # pydantic-settings permite setear atributos en la instancia. Si no,
    # recargar el módulo también funciona; acá probamos el camino simple.
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", True)
    assert settings.GOVERNANCE_LLM_ENABLED is True
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    assert settings.GOVERNANCE_LLM_ENABLED is False


# ============================================================ chokepoint NIM


def test_nim_generate_devuelve_None_cuando_flag_apagada_y_key_disponible(monkeypatch):
    """A9: con flag apagada, generate() devuelve None ANTES de hacer request,
    incluso si la key está configurada. Esto protege la cuota."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    # Simulamos que hay key (la flag debe ganar sobre la disponibilidad).
    nim = NvidiaNIMClient(api_key="sk-fake-key")
    assert nim.is_available() is True  # la key está, pero la flag manda
    with mock.patch("app.core.advanced_agents.requests.post") as mp:
        out = nim.generate("sys", "user")
    assert out is None
    assert mp.called is False, "requests.post NO debe invocarse con flag apagada"


def test_nim_generate_procede_cuando_flag_encendida(monkeypatch):
    """Escape hatch: con flag=True, generate() llama requests.post normalmente."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", True)
    nim = NvidiaNIMClient(api_key="sk-fake-key")
    fake_resp = mock.Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "ok"}}]})
    with mock.patch("app.core.advanced_agents.requests.post", return_value=fake_resp) as mp:
        out = nim.generate("sys", "user")
    assert out == "ok"
    assert mp.called is True


def test_nim_generate_sigue_fallando_cuando_no_hay_key(monkeypatch):
    """Si no hay key (caso pre-existente), sigue devolviendo None — la flag
    no inventa disponibilidad que no existe."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", True)
    nim = NvidiaNIMClient(api_key="")
    assert nim.is_available() is False
    out = nim.generate("sys", "user")
    assert out is None


# ============================================================ predict endpoint


def _fake_result():
    cons = SimpleNamespace(bull_score=0.5, bear_score=-0.2, contrarian_score=0.1)
    return SimpleNamespace(
        symbol="TESTA", timestamp="2024-01-02T00:00:00",
        regime_state=0, regime_name="GOLDILOCKS",
        technical_score=0.3, fundamental_score=0.1, macro_score=0.2,
        sentiment_score=0.0, volatility_score=0.1, composite_score=0.55,
        decision="COMPRAR", confidence=0.7,
        motor="heuristico_no_validado",
        probabilidades_calibradas=False,
        prob_up_short=0.6, prob_up_medium=0.55, prob_up_long=0.52,
        manipulation_risk=0.05, manipulation_signals=[],
        triad_score=0.4, triad_recommendation="COMPRAR", triad_agreement="ALTO",
        triad_consensus=cons,
        signals=[
            SimpleNamespace(name="rsi14", category="momentum", value=58.0,
                            signal=1.0, weight=0.2, explanation="RSI sano")
        ],
    )


def _patch_predict_io(monkeypatch, ohlcv_df):
    monkeypatch.setattr(PredictiveEngine, "analyze", lambda self, **kw: _fake_result())
    monkeypatch.setattr(pred_route, "download_data", lambda s, start=None: ohlcv_df)
    monkeypatch.setattr(pred_route, "_load_macro_data", lambda: {})
    monkeypatch.setattr(pred_route, "_load_sentiment_data", lambda: None)
    monkeypatch.setattr(pred_route, "get_fundamentals_api", lambda symbol: None)
    pred_route._data_cache = None
    pred_route._data_cache_time = 0.0


def test_analyze_symbol_payload_incluye_governance_mode_descriptive(monkeypatch, ohlcv_df):
    """A9: con flag apagada (default), el payload lleva governance_mode='descriptive_only'."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    _patch_predict_io(monkeypatch, ohlcv_df)
    body = asyncio.run(pred_route.analyze_symbol("TESTA"))
    assert "governance_mode" in body
    assert body["governance_mode"] == "descriptive_only"


def test_analyze_symbol_payload_incluye_governance_mode_active(monkeypatch, ohlcv_df):
    """A9: con flag encendida, governance_mode='active'."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", True)
    _patch_predict_io(monkeypatch, ohlcv_df)
    body = asyncio.run(pred_route.analyze_symbol("TESTA"))
    assert body["governance_mode"] == "active"


# ============================================================ governance status


def test_governance_status_expone_flags(monkeypatch):
    """A9: el endpoint /status expone governance_llm_enabled y
    nvidia_nim_blocked_by_a9 para que el dashboard pueda renderizar el
    cartel 'descriptiva — no conectada a decisiones'."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    # Stub de la disponibilidad de NIM (sin tocar red). El endpoint
    # /status lee `nim.model`, `nim.base_url`, etc. — el stub tiene
    # los atributos exactos que el handler espera.
    def _stub_nim(*a, **kw):
        return SimpleNamespace(
            is_available=lambda: False,
            model="meta/llama-3.1-8b-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
        )
    monkeypatch.setattr(gov_route, "NvidiaNIMClient", _stub_nim)
    out = asyncio.run(gov_route.get_governance_status())
    assert "governance_llm_enabled" in out
    assert out["governance_llm_enabled"] is False
    assert "nvidia_nim_blocked_by_a9" in out
    assert out["nvidia_nim_blocked_by_a9"] is False  # no hay key, no hay bloqueo


def test_governance_status_nim_blocked_only_when_key_and_flag_off(monkeypatch):
    """nvidia_nim_blocked_by_a9=True SOLO si (flag apagada) Y (key configurada)."""
    def _stub_nim(*a, **kw):
        return SimpleNamespace(
            is_available=lambda: True,
            model="meta/llama-3.1-8b-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
        )
    monkeypatch.setattr(gov_route, "NvidiaNIMClient", _stub_nim)

    # Caso: key configurada + flag off => bloqueado por A9
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    out = asyncio.run(gov_route.get_governance_status())
    assert out["governance_llm_enabled"] is False
    assert out["nvidia_nim_blocked_by_a9"] is True

    # Caso: key configurada + flag on => NO bloqueado (escape hatch)
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", True)
    out = asyncio.run(gov_route.get_governance_status())
    assert out["governance_llm_enabled"] is True
    assert out["nvidia_nim_blocked_by_a9"] is False


# ============================================================ governance analyze


def _stub_governance_process(*args, **kwargs):
    """Stubea GovernanceSystem.process_governance (sin red, sin RAG)."""
    return {
        "triad": {"bull": {"score": 0.0, "verdict": "MANTENER"},
                  "bear": {"score": 0.0, "verdict": "MANTENER"},
                  "contrarian": {"score": 0.0, "verdict": "MANTENER"},
                  "consensus": 0.0, "decision": "MANTENER", "agreement": "DESHABILITADO"},
        "controller": {"approved": False, "decision": "MANTENER"},
        "judge": {"verdict": "MANTENER", "overruled_agents": []},
        "final_decision": "MANTENER",
        "final_reason": "deterministic fallback",
    }


def test_governance_analyze_etiqueta_final_reason_cuando_flag_apagada(monkeypatch):
    """A9: con flag apagada, el final_reason del response lleva el tag
    GOVERNANCE_LLM_DISABLED_BY_A9 (para que el dashboard no confunda el
    'MANTENER' determinista con una decisión real de governance)."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", False)
    monkeypatch.setattr(GovernanceSystem, "process_governance", _stub_governance_process)
    monkeypatch.setattr(gov_route, "download_data", lambda s, start=None: _ohlcv_min())
    monkeypatch.setattr(gov_route, "_load_macro_data", lambda: {})
    monkeypatch.setattr(gov_route, "get_fundamentals_api", lambda s: None)
    monkeypatch.setattr(PredictiveEngine, "analyze", lambda self, **kw: _fake_result())

    out = asyncio.run(gov_route.analyze_with_governance("TESTA"))
    assert out["governance_mode"] == "descriptive_only"
    assert "GOVERNANCE_LLM_DISABLED_BY_A9" in out["governance"]["final_reason"]


def test_governance_analyze_no_etiqueta_cuando_flag_encendida(monkeypatch):
    """A9: con flag encendida, NO se mete el tag (modo activo)."""
    monkeypatch.setattr(settings, "GOVERNANCE_LLM_ENABLED", True)
    monkeypatch.setattr(GovernanceSystem, "process_governance", _stub_governance_process)
    monkeypatch.setattr(gov_route, "download_data", lambda s, start=None: _ohlcv_min())
    monkeypatch.setattr(gov_route, "_load_macro_data", lambda: {})
    monkeypatch.setattr(gov_route, "get_fundamentals_api", lambda s: None)
    monkeypatch.setattr(PredictiveEngine, "analyze", lambda self, **kw: _fake_result())

    out = asyncio.run(gov_route.analyze_with_governance("TESTA"))
    assert out["governance_mode"] == "active"
    assert "GOVERNANCE_LLM_DISABLED_BY_A9" not in out["governance"]["final_reason"]


# ============================================================ regresión D1


def test_signal_engine_NO_usa_governance_llm_flag():
    """Regresión D1 (AUDITORIA_NIVEL_DIOS_20260902): el motor validado
    `signal_engine.py` NO consulta `GOVERNANCE_LLM_ENABLED` ni la capa
    multi-agente. Esto es lo que permite que A9 apague la capa sin
    afectar el gate. Si alguien toca esto, este test rompe ruidoso."""
    import subprocess
    # Grep sobre signal_engine.py: no debe mencionar GOVERNANCE_LLM_ENABLED
    # ni importar advanced_agents / governance
    r = subprocess.run(
        ["grep", "-l", "GOVERNANCE_LLM_ENABLED", "app/core/signal_engine.py"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert r.stdout.strip() == "", (
        f"signal_engine.py NO debe tocar GOVERNANCE_LLM_ENABLED (D1).\n"
        f"Match: {r.stdout!r}"
    )
    r2 = subprocess.run(
        ["grep", "-E", "from app\\.core\\.advanced_agents|from app\\.api\\.routes\\.governance",
         "app/core/signal_engine.py"],
        capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert r2.stdout.strip() == "", (
        f"signal_engine.py NO debe importar la capa multi-agente (D1).\n"
        f"Match: {r2.stdout!r}"
    )


# ============================================================ helper


def _ohlcv_min():
    """DataFrame mínimo que pasa el `if len(df) < 200` de governance analyze."""
    import pandas as pd
    n = 250
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
        index=idx,
    )
