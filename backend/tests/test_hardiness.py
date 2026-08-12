"""Tests de HardinessChecker (movido de prompt_engine.py a app/core/hardiness.py).

Portados intactos de scripts/test_prompt_engine.py::test_hardiness, que se
eliminó junto con prompt_engine.py (código muerto). HardinessChecker se usa
en triad_agents.py para validar las respuestas LLM antes de confiar en ellas.
"""

from app.core.hardiness import HardinessChecker


def test_valid_json_response():
    data, errors = HardinessChecker.validate_json_response(
        '{"score": 0.5, "confidence": 0.7, "reasoning": "Tendencia alcista clara con volumen"}'
    )
    assert data is not None and not errors


def test_invalid_json_response():
    data, errors = HardinessChecker.validate_json_response("no es json")
    assert data is None and errors


def test_score_out_of_range():
    data, errors = HardinessChecker.validate_json_response(
        '{"score": 5.0, "confidence": 0.7, "reasoning": "test razonamiento largo"}'
    )
    assert data is None and errors


def test_missing_required_field():
    data, errors = HardinessChecker.validate_json_response(
        '{"score": 0.5, "reasoning": "test razonamiento largo"}'
    )
    assert data is None and any("confidence" in e for e in errors)


def test_deviation_from_deterministic():
    ok, msg = HardinessChecker.validate_against_deterministic(0.8, 0.1)
    assert not ok and "Desviación" in msg
    ok, msg = HardinessChecker.validate_against_deterministic(0.35, 0.3)
    assert ok


def test_confidence_consistency():
    ok, _ = HardinessChecker.validate_confidence_consistency(0.05, 0.9)
    assert not ok
    ok, _ = HardinessChecker.validate_confidence_consistency(0.8, 0.2)
    assert not ok
    ok, _ = HardinessChecker.validate_confidence_consistency(0.4, 0.6)
    assert ok


def test_hallucination_detection():
    # Formato soportado: "clave: valor" o "clave = valor" (regex adyacente).
    # Nota: el assert del script original que portamos (texto libre "El RSI es 99.5")
    # nunca pudo pasar — era el "bug latente" de prompt_engine.py.
    hals = HardinessChecker.detect_hallucination(
        "rsi14: 99.5, close: 500", {"rsi14": 55.0, "close": 150.0}
    )
    assert len(hals) >= 2
    assert not HardinessChecker.detect_hallucination(
        "rsi14 = 55.0, close: 150.0", {"rsi14": 55.0, "close": 150.0}
    )
