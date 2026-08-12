"""
Regresión del contrato GovernancePanel (frontend) <-> process_governance (backend).

El bug que este test previene: el frontend esperaba `governance.triad_consensus.*`,
`controller_approved` y `judge_verdict` planos; el backend envía
`governance.triad.{bull,bear,contrarian}.score`, `controller.approved` y
`judge.verdict|status` — el panel renderizaba "RECHAZADO" y "undefined" siempre,
sin crashear (fetch tipado `any`). Cualquier cambio en el shape de
process_governance que rompa el contrato debe fallar acá.
"""
import pytest

from app.core.advanced_agents import GovernanceSystem
from app.core.knowledge_repo import RAGMemorySystem


def _run_governance(triad_data=None, monkeypatch=None):
    """Ejecuta process_governance sin llamadas a red ni escrituras a disco:
    NIM no disponible sin key; RAG memory con _save neutralizado."""
    sys = GovernanceSystem(memory_file=":memory:")
    if monkeypatch is not None:
        monkeypatch.setattr(RAGMemorySystem, "_save", lambda self: None)
        monkeypatch.setattr(
            sys.professor, "_save_memory", lambda: None,
        )
    triad = triad_data or {
        "bull_score": 0.6, "bear_score": -0.2, "contrarian_score": 0.1,
        "triad_score": 0.5, "triad_recommendation": "COMPRAR",
        "triad_agreement": "ALTO",
    }
    return sys.process_governance(
        symbol="TEST", triad_data=triad, composite_score=0.3,
        regime_state=0, current_drawdown=0.0, current_exposure=0.0,
        manipulation_risk=0.1, macro_score=0.2,
    )


def test_governance_contract_triad_shape(monkeypatch):
    """El frontend lee governance.triad.bull/bear/contrarian.score."""
    result = _run_governance(monkeypatch=monkeypatch)
    triad = result["triad"]
    assert set(triad.keys()) == {"bull", "bear", "contrarian", "consensus", "decision", "agreement"}
    for agent in ("bull", "bear", "contrarian"):
        assert set(triad[agent].keys()) == {"score", "verdict"}
        assert isinstance(triad[agent]["score"], (int, float))


def test_governance_contract_controller_approved(monkeypatch):
    """El frontend lee governance.controller.approved (bool)."""
    result = _run_governance(monkeypatch=monkeypatch)
    controller = result["controller"]
    assert isinstance(controller["approved"], bool)
    assert "decision" in controller


def test_governance_contract_judge_shape(monkeypatch):
    """El frontend lee governance.judge.verdict o .status y .overruled_agents."""
    result = _run_governance(monkeypatch=monkeypatch)
    judge = result["judge"]
    assert ("verdict" in judge and "overruled_agents" in judge) or "status" in judge
    if "overruled_agents" in judge:
        assert isinstance(judge["overruled_agents"], list)


def test_governance_contract_final_fields(monkeypatch):
    """El frontend lee governance.final_decision y final_reason."""
    result = _run_governance(monkeypatch=monkeypatch)
    assert result["final_decision"] in ("COMPRAR", "VENDER", "MANTENER", "COMPRAR_FUERTE", "VENDER_FUERTE")
    assert isinstance(result["final_reason"], str) and result["final_reason"]


def test_governance_contract_no_legacy_flat_fields(monkeypatch):
    """El shape viejo (triad_consensus/controller_approved/judge_verdict planos) NO debe volver."""
    result = _run_governance(monkeypatch=monkeypatch)
    assert "triad_consensus" not in result
    assert "controller_approved" not in result
    assert "judge_verdict" not in result
    assert "judge_overrides" not in result