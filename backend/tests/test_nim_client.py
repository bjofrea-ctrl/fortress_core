from unittest.mock import patch

from app.core.advanced_agents import NvidiaNIMClient


def test_explicit_empty_api_key_does_not_fall_back_to_settings():
    """
    Regresión: `self.api_key = api_key or NVIDIA_NIM_CONFIG["api_key"]`
    trataba "" como "no proveída" (string vacío es falsy en Python) y caía
    igual a la key real configurada en Settings. Esto invalidó comparaciones
    "con LLM vs sin LLM" en varios scripts de diagnóstico de esta sesión,
    que dependían de api_key="" para forzar modo 100% determinista.
    """
    with patch("app.core.advanced_agents.NVIDIA_NIM_CONFIG", {
        "base_url": "https://fake", "model": "fake-model",
        "api_key": "una-key-real-configurada", "temperature": 0.3, "max_tokens": 2048,
    }):
        forced_empty = NvidiaNIMClient(api_key="")
        assert forced_empty.api_key == ""
        assert forced_empty.is_available() is False

        using_default = NvidiaNIMClient(api_key=None)
        assert using_default.api_key == "una-key-real-configurada"
        assert using_default.is_available() is True
