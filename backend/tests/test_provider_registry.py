"""C2: PROVIDER_REGISTRY (TradingAgents openai_client.OPENAI_COMPATIBLE_PROVIDERS)."""
import importlib

import pytest


def test_registry_structure():
    from app.core.advanced_agents import PROVIDER_REGISTRY

    assert isinstance(PROVIDER_REGISTRY, dict)
    assert set(PROVIDER_REGISTRY) == {"kimi-k3", "minimax-m3", "glm-5.2"}
    for name, spec in PROVIDER_REGISTRY.items():
        assert set(spec.keys()) == {"base_url", "settings_key", "structured", "wire_id"}, name
        assert isinstance(spec["base_url"], str) and spec["base_url"].strip()
        assert isinstance(spec["settings_key"], str) and spec["settings_key"].strip()
        assert isinstance(spec["structured"], bool)
        assert isinstance(spec["wire_id"], str) and spec["wire_id"].strip()


def test_triad_and_governance_use_registry_keys():
    from app.core.advanced_agents import GOVERNANCE_LLM_MODELS, PROVIDER_REGISTRY, TRIAD_LLM_MODELS

    for agent, slug in {**TRIAD_LLM_MODELS, **GOVERNANCE_LLM_MODELS}.items():
        assert slug in PROVIDER_REGISTRY, f"{agent} -> {slug} not in PROVIDER_REGISTRY"


def test_resolve_provider_uses_registry():
    from unittest.mock import patch

    from app.core.advanced_agents import NvidiaNIMClient

    client = NvidiaNIMClient(model="kimi-k3", api_key="key", is_triad_client=True)
    with patch("app.core.advanced_agents.settings") as ms:
        ms.NVIDIA_NIM_API_KEY = "nv-key"
        ms.OPENROUTER_API_KEY = "or-key"
        ms.NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
        ms.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        url, key, wire = client._resolve_provider("kimi-k3")
        assert url == "https://integrate.api.nvidia.com/v1/chat/completions"
        assert key == "nv-key"
        assert wire == "moonshotai/kimi-k3"

        url2, key2, wire2 = client._resolve_provider("minimax-m3")
        assert url2 == "https://openrouter.ai/api/v1/chat/completions"
        assert key2 == "or-key"
        assert wire2 == "minimax/minimax-m3:free"

        url3, key3, wire3 = client._resolve_provider("glm-5.2")
        assert wire3 == "z-ai/glm-5.2:free"
        assert key3 == "or-key"


def test_unknown_slug_raises():
    from app.core.advanced_agents import NvidiaNIMClient

    client = NvidiaNIMClient(model="kimi-k3", api_key="key", is_triad_client=True)
    with pytest.raises(ValueError, match="not registered"):
        client._resolve_provider("unknown-model")


def test_validation_catches_unregistered_slug():
    from app.core import advanced_agents

    orig = advanced_agents.TRIAD_LLM_MODELS.copy()
    try:
        advanced_agents.TRIAD_LLM_MODELS["BULL"] = "no-existe"
        with pytest.raises(ValueError, match="not in PROVIDER_REGISTRY"):
            advanced_agents._validate_provider_registry()
    finally:
        advanced_agents.TRIAD_LLM_MODELS.clear()
        advanced_agents.TRIAD_LLM_MODELS.update(orig)


def test_validation_catches_missing_settings_key():
    from app.core import advanced_agents

    orig = advanced_agents.PROVIDER_REGISTRY["kimi-k3"].copy()
    try:
        advanced_agents.PROVIDER_REGISTRY["kimi-k3"]["settings_key"] = "KEY_INEXISTENTE_XYZ"
        with pytest.raises(ValueError, match="not found in Settings"):
            advanced_agents._validate_provider_registry()
    finally:
        advanced_agents.PROVIDER_REGISTRY["kimi-k3"] = orig


def test_registry_import_revalidates():
    # Reimport must still pass validation (no spurious failure)
    mod = importlib.import_module("app.core.advanced_agents")
    assert hasattr(mod, "PROVIDER_REGISTRY")
    assert hasattr(mod, "_validate_provider_registry")
