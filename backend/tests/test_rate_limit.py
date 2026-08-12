"""Tests del rate limit en memoria para endpoints LLM sin auth."""
from typing import Dict, Optional
from unittest import mock

import pytest
from app.api.rate_limit import RateLimitDependency
from fastapi import HTTPException


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, host: str, headers: Optional[Dict[str, str]] = None):
        self.client = _FakeClient(host)
        self.headers = headers or {}


def test_rate_limit_bloquea_al_exceder_el_limite():
    dep = RateLimitDependency(max_calls=3, window_seconds=60)
    req = _FakeRequest(host="1.2.3.4")

    for _ in range(3):
        dep(req)

    with pytest.raises(HTTPException) as exc:
        dep(req)
    assert exc.value.status_code == 429


def test_rate_limit_distingue_por_ip():
    dep = RateLimitDependency(max_calls=2, window_seconds=60)

    for _ in range(2):
        dep(_FakeRequest(host="10.0.0.1"))

    dep(_FakeRequest(host="10.0.0.2"))
    dep(_FakeRequest(host="10.0.0.2"))

    with pytest.raises(HTTPException):
        dep(_FakeRequest(host="10.0.0.2"))


def test_rate_limit_resetea_al_vencer_la_ventana():
    dep = RateLimitDependency(max_calls=1, window_seconds=60)
    req = _FakeRequest(host="10.0.0.3")

    with mock.patch("app.api.rate_limit.time.monotonic", side_effect=[0.0, 0.0, 61.0]):
        dep(req)  # t=0 → registra
        with pytest.raises(HTTPException):
            dep(req)  # t=0 → bloquea
        dep(req)  # t=61 → ventana vencida, entra de nuevo


def test_rate_limit_usa_x_forwarded_for_cuando_existe():
    dep = RateLimitDependency(max_calls=1, window_seconds=60)
    req = _FakeRequest(host="1.2.3.4", headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1"})

    dep(req)
    with pytest.raises(HTTPException):
        dep(req)
