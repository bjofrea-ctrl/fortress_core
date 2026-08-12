"""
Regresión de verify_api_key (governance.py): comparación tiempo-constante y
rechazo de key faltante/incorrecta. El bug que este test previene: comparación
`!=` (no hmac.compare_digest) y default SECRET_KEY inseguro en config.
"""
import pytest
from app.api.routes.governance import verify_api_key
from app.config import settings
from fastapi import HTTPException


def test_verify_api_key_accepts_correct_key():
    verify_api_key(x_api_key=settings.SECRET_KEY)


def test_verify_api_key_rejects_wrong_key():
    with pytest.raises(HTTPException) as exc:
        verify_api_key(x_api_key="wrong-key")
    assert exc.value.status_code == 401


def test_verify_api_key_rejects_missing_key():
    with pytest.raises(HTTPException) as exc:
        verify_api_key(x_api_key=None)
    assert exc.value.status_code == 401


def test_verify_api_key_timing_constant_comparison():
    """La comparación debe hacerse con hmac.compare_digest (tiempo-constante)."""
    import hmac
    import inspect

    src = inspect.getsource(verify_api_key)
    assert "hmac.compare_digest" in src, "verify_api_key debe usar hmac.compare_digest"
    assert hmac.compare_digest("a", "b") is False  # sanity: API existe en 3.9


def test_secret_key_default_blocked_outside_development():
    """ENVIRONMENT != development + SECRET_KEY default -> Settings debe fallar."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        settings.__class__(ENVIRONMENT="production", SECRET_KEY="change-me-in-production", _env_file=None)
