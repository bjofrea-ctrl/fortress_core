"""Tests de integración del router /api/system."""
import asyncio

from app.api.routes import system
from app.core.advanced_agents import NvidiaNIMClient


def test_status_con_llm_habilitado(monkeypatch):
    monkeypatch.setattr(NvidiaNIMClient, "is_available", lambda self: True)
    body = asyncio.run(system.system_status())
    assert body["risk_manager_active"] is True
    assert body["absolute_ceiling"] > 0
    assert body["ai_agents_enabled"] is True
    assert "4" in body["phase"]


def test_status_sin_llm(monkeypatch):
    monkeypatch.setattr(NvidiaNIMClient, "is_available", lambda self: False)
    body = asyncio.run(system.system_status())
    assert body["ai_agents_enabled"] is False
    assert "1-3" in body["phase"]
