from unittest.mock import Mock, patch

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


# C1: retry/backoff con llm_max_retries (TradingAgents llm_clients/factory.py)


def _fake_response(status_code, headers=None, json_data=None):
    m = Mock()
    m.status_code = status_code
    m.headers = headers or {}
    if json_data is not None:
        m.json.return_value = json_data
    return m


def test_generate_retries_429_then_succeeds():
    """429 -> 429 -> 200 debe exigir 3 intentos y éxito (C1)."""
    client = NvidiaNIMClient(model="kimi-k3", api_key="key", is_triad_client=True)
    ok_payload = {"choices": [{"message": {"content": "hello"}}]}
    r429 = _fake_response(429)
    r200 = _fake_response(200, json_data=ok_payload)
    with patch("app.core.advanced_agents.settings") as mock_settings:
        mock_settings.GOVERNANCE_LLM_ENABLED = True
        mock_settings.LLM_MAX_RETRIES = 2
        mock_settings.NVIDIA_NIM_API_KEY = "fake-nvidia-key"
        mock_settings.OPENROUTER_API_KEY = "fake-or-key"
        mock_settings.NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        # is_available checks client.api_key, no need to patch settings for that,
        # pero _resolve_provider lee settings.NVIDIA_NIM_API_KEY
        with patch("app.core.advanced_agents.requests.post", side_effect=[r429, r429, r200]) as mock_post:
            with patch("app.core.advanced_agents.time.sleep") as mock_sleep:
                with patch("app.core.advanced_agents.random.uniform", return_value=1.0):
                    out = client.generate("sys", "user", model="kimi-k3")
                    assert out == "hello"
                    assert mock_post.call_count == 3
                    # 2 sleeps (entre intento 1-2 y 2-3)
                    assert mock_sleep.call_count == 2


def test_generate_max_retries_zero_reproduces_current_behavior():
    """max_retries=0 debe reproducir comportamiento actual exacto: sin reintento."""
    client = NvidiaNIMClient(model="kimi-k3", api_key="key", is_triad_client=True)
    r429 = _fake_response(429)
    with patch("app.core.advanced_agents.settings") as mock_settings:
        mock_settings.GOVERNANCE_LLM_ENABLED = True
        mock_settings.LLM_MAX_RETRIES = 0
        mock_settings.NVIDIA_NIM_API_KEY = "fake-nvidia-key"
        mock_settings.OPENROUTER_API_KEY = "fake-or-key"
        mock_settings.NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        with patch("app.core.advanced_agents.requests.post", return_value=r429) as mock_post:
            with patch("app.core.advanced_agents.time.sleep") as mock_sleep:
                out = client.generate("sys", "user", model="kimi-k3")
                assert out is None
                assert mock_post.call_count == 1
                mock_sleep.assert_not_called()


def test_generate_respects_retry_after_header():
    """Debe respetar Retry-After cuando está presente (TradingAgents reddit.py)."""
    client = NvidiaNIMClient(model="kimi-k3", api_key="key", is_triad_client=True)
    r429_ra = _fake_response(429, headers={"Retry-After": "2"})
    r200 = _fake_response(200, json_data={"choices": [{"message": {"content": "ok"}}]})
    with patch("app.core.advanced_agents.settings") as mock_settings:
        mock_settings.GOVERNANCE_LLM_ENABLED = True
        mock_settings.LLM_MAX_RETRIES = 1
        mock_settings.NVIDIA_NIM_API_KEY = "fake-nvidia-key"
        mock_settings.OPENROUTER_API_KEY = "fake-or-key"
        mock_settings.NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        with patch("app.core.advanced_agents.requests.post", side_effect=[r429_ra, r200]) as mock_post:
            with patch("app.core.advanced_agents.time.sleep") as mock_sleep:
                out = client.generate("sys", "user", model="kimi-k3")
                assert out == "ok"
                assert mock_post.call_count == 2
                # debe haber dormido exactamente 2.0 (Retry-After), no jitter
                assert mock_sleep.call_args[0][0] == 2.0


def test_generate_backoff_with_jitter_when_no_retry_after():
    """Sin Retry-After: backoff exponencial con jitter."""
    client = NvidiaNIMClient(model="kimi-k3", api_key="key", is_triad_client=True)
    r429 = _fake_response(429)
    r429_2 = _fake_response(429)
    r200 = _fake_response(200, json_data={"choices": [{"message": {"content": "ok2"}}]})
    with patch("app.core.advanced_agents.settings") as mock_settings:
        mock_settings.GOVERNANCE_LLM_ENABLED = True
        mock_settings.LLM_MAX_RETRIES = 2
        mock_settings.NVIDIA_NIM_API_KEY = "fake-nvidia-key"
        mock_settings.OPENROUTER_API_KEY = "fake-or-key"
        mock_settings.NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        with patch("app.core.advanced_agents.requests.post", side_effect=[r429, r429_2, r200]):
            with patch("app.core.advanced_agents.time.sleep") as mock_sleep:
                with patch("app.core.advanced_agents.random.uniform", return_value=1.0):
                    out = client.generate("sys", "user", model="kimi-k3")
                    assert out == "ok2"
                    # primer wait ~1.0, segundo ~2.0 (backoff*2)
                    waits = [c[0][0] for c in mock_sleep.call_args_list]
                    assert waits[0] == 1.0
                    assert waits[1] == 2.0
