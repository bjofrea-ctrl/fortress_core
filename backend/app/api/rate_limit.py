"""Rate limiting básico en memoria para endpoints sin auth que disparan LLM real.

Estos endpoints exponen costo/cuota de NVIDIA NIM a cualquiera sin autenticarse.
No protege datos (no los expone): protege el presupuesto. Ventana deslizante
por IP con log de uso, sin dependencias externas (no hay Redis en el stack).
"""
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request

from app.utils.logging import logger

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_CALLS = 10

_lock = threading.Lock()
_calls: Dict[str, Deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitDependency:
    """Dependencia FastAPI: ventana deslizante por IP, 429 al exceder el límite."""

    def __init__(self, max_calls: int = RATE_LIMIT_MAX_CALLS,
                 window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_calls = max_calls
        self.window_seconds = window_seconds

    def __call__(self, request: Request) -> None:
        key = _client_key(request)
        now = time.monotonic()

        with _lock:
            window = _calls.pop(key, None) or deque()
            while window and now - window[0] > self.window_seconds:
                window.popleft()
            if len(window) >= self.max_calls:
                _calls[key] = window
                logger.warning(
                    "Rate limit excedido: %s (%d llamadas en %ds)",
                    key, len(window), self.window_seconds,
                )
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests: límite de llamadas LLM alcanzado",
                )
            window.append(now)
            if window:
                _calls[key] = window

        logger.info(
            "Llamada a endpoint LLM desde %s (%d en los últimos %ds)",
            key, len(window), self.window_seconds,
        )
