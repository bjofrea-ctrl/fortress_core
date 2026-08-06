"""Prueba del Prompt Engine nivel dios."""
import sys, os
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.prompt_engine import (
    PromptEngine, MemorySystem, HardinessChecker,
    GOD_LEVEL_PROMPTS, COT_TEMPLATES, FEW_SHOT_EXAMPLES,
)


def test_memory():
    print("\n=== TEST 1: MemorySystem ===")
    mem = MemorySystem("data/test_memory.json")
    mem.add("AAPL tendencia alcista con RSI saludable", "pattern", 0.8, ["AAPL", "bull"])
    mem.add("SPY en distribución con CMF negativo", "warning", 0.9, ["SPY", "bear"])
    mem.add("NVDA momentum fuerte 12m", "fact", 0.6, ["NVDA"])
    ctx = mem.get_context("AAPL tendencia")
    print(f"  Context: {ctx[:100]}...")
    stats = mem.get_stats()
    print(f"  Stats: {stats}")
    assert len(mem.short_term) >= 3
    print("  OK")


def test_hardiness():
    """Test 2: HardinessChecker."""
    print("\n=== Test 2: HardinessChecker ===")
    hc = HardinessChecker()

    # JSON válido
    data, errors = hc.validate_json_response(
        '{"score": 0.5, "confidence": 0.7, "reasoning": "Tendencia alcista clara con volumen"}'
    )
    print(f"  Valid JSON: {data is not None}, errors={errors}")
    assert data is not None and not errors

    # JSON inválido
    data, errors = hc.validate_json_response("no es json")
    print(f"  Invalid JSON: {data is None}, errors={errors}")
    assert data is None

    # Score fuera de rango
    data, errors = hc.validate_json_response(
        '{"score": 5.0, "confidence": 0.7, "reasoning": "test razonamiento largo"}'
    )
    print(f"  Score out of range: {data is None}, errors={errors}")
    assert data is None

    # Desviación vs determinista
    ok, msg = hc.validate_against_deterministic(0.8, 0.1)
    print(f"  Deviation check: ok={ok}, msg={msg}")
    assert not ok

    # Confianza inconsistente
    ok, msg = hc.validate_confidence_consistency(0.05, 0.9)
    print(f"  Confidence check: ok={ok}, msg={msg}")
    assert not ok

    # Alucinación
    hals = hc.detect_hallucination("El RSI es 99.5 y el precio es 500", {"rsi14": 55.0})
    print(f"  Hallucinations: {hals}")
    assert len(hals) > 0
    print("  OK")


def test_prompts():
    """Test 3: God level prompts."""
    print("\n=== Test 3: GodLevelPrompts ===")
    for agent in ["BULL", "BEAR", "CONTRARIAN", "JUDGE", "PROFESSOR"]:
        prompt = GOD_LEVEL_PROMPTS[agent]
        print(f"  {agent}: {len(prompt)} chars")
        assert len(prompt) > 200
    assert len(COT_TEMPLATES) >= 3
    assert len(FEW_SHOT_EXAMPLES) >= 3
    print("  OK")


def test_prompt_engine():
    """Test 4: PromptEngine integrado."""
    print("\n=== Test 4: PromptEngine ===")
    engine = PromptEngine("data/test_prompt_memory.json")

    # System prompt
    sys_prompt = engine.build_system_prompt("BULL")
    print(f"  System prompt: {len(sys_prompt)} chars")
    assert "NIVEL DIOS" in sys_prompt
    assert "JSON" in sys_prompt

    # User message
    data = {"symbol": "AAPL", "close": 150.0, "rsi14": 58.0, "ema20": 148.0}
    user_msg = engine.build_user_message("BULL", data, deterministic_score=0.3)
    print(f"  User message: {len(user_msg)} chars")
    assert "SCORE DETERMINISTA" in user_msg

    # Procesar respuesta válida
    resp = '{"score": 0.4, "confidence": 0.7, "reasoning": "Tendencia alcista confirmada con volumen", "signals": ["EMA alcista"]}'
    data, errors = engine.process_llm_response(resp, "BULL", deterministic_score=0.3)
    print(f"  Valid response: {data is not None}, errors={errors}")
    assert data is not None and not errors

    # Procesar respuesta con alucinación
    resp_bad = '{"score": 0.9, "confidence": 0.9, "reasoning": "El precio es 5000 y RSI es 99", "signals": []}'
    data, errors = engine.process_llm_response(
        resp_bad, "BULL", deterministic_score=0.3,
        known_values={"close": 150.0, "rsi14": 58.0}
    )
    print(f"  Hallucination response: data={data is not None}, errors={errors}")
    assert len(errors) > 0

    # Self-consistency
    responses = [
        '{"score": 0.4, "confidence": 0.7, "reasoning": "Tendencia alcista con volumen"}',
        '{"score": 0.5, "confidence": 0.8, "reasoning": "Momentum positivo con MACD alcista"}',
        '{"score": 0.3, "confidence": 0.6, "reasoning": "Señales mixtas pero sesgo alcista"}',
    ]
    best, consistency = engine.self_consistency(responses, "BULL", deterministic_score=0.3)
    print(f"  Self-consistency: score={best['score'] if best else None}, consistency={consistency:.3f}")
    assert best is not None and consistency > 0.5

    # Status
    status = engine.get_status()
    print(f"  Status: {status['agents']}")
    print("  OK")


if __name__ == "__main__":
    print("=" * 60)
    print("FORTRESS CORE - TEST PROMPT ENGINE NIVEL DIOS")
    print("=" * 60)
    test_memory()
    test_hardiness()
    test_prompts()
    test_prompt_engine()
    print("\n" + "=" * 60)
    print("TODAS LAS PRUEBAS DEL PROMPT ENGINE PASARON")
    print("=" * 60)