""API routes para el sistema de gobernanza de agentes Fortress Core.

Flujo: Tríada (BULL, BEAR, CONTRARIAN) → CONTROLADOR → discusión con PROFESOR
→ Si no hay consenso → JUEZ decide. PROFESOR educa usando RAG/OKF.
"""
from fastapi import APIRouter, HTTPException, Query, Header, Depends
import os

from app.config import settings
from app.core.data_ingestion import download_data
from app.core.predictive_engine import PredictiveEngine
from app.core.advanced_agents import (
    GovernanceSystem,
    NvidiaNIMClient,
    AGENT_PROMPTS,
    NVIDIA_MODELS,
    GOVERNANCE_LLM_MODELS,
    TRIAD_LLM_MODELS,
    JUDGE_PROMPT,
    PROFESSOR_PROMPT,
    CONTROLLER_PROMPT,
)
from app.core.knowledge_repo import KnowledgeRepository, RAGMemorySystem, OKF_STRUCTURE

router = APIRouter(prefix="/api/governance", tags=["governance"])

CACHE_DIR = "data/cache"


def verify_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> None:
    """
    Protege rutas de escritura: requiere X-API-Key == settings.SECRET_KEY.
    Escritas sin auth antes permitían que cualquiera inyecte contenido en el
    repositorio RAG (leído después por el prompt de PROFESOR) o envenene el
    historial de aciertos de los agentes vía /record-prediction.
    """
    if not x_api_key or x_api_key != settings.SECRET_KEY:
        raise HTTPException(status_code=401, detail="X-API-Key inválida o faltante")


@router.get("/status")
async def get_governance_status():
    """Estado del sistema de gobernanza con RAG/OKF."""
    governance = GovernanceSystem()
    nim = NvidiaNIMClient()
    repo = KnowledgeRepository()
    rag = RAGMemorySystem()

    return {
        "flow": "TRIAD → CONTROLLER ↔ PROFESSOR → JUDGE (si no hay consenso)",
        "traid_llm_models": TRIAD_LLM_MODELS,
        "governance_llm_models": GOVERNANCE_LLM_MODELS,
        "professor": {
            "lessons_count": len(governance.professor.lessons),
            "weight_adjustments": governance.professor.weight_adjustments,
            "teaching_summary": governance.professor.get_teaching_summary(),
        },
        "controller": {
            "absolute_ceiling": governance.controller.absolute_ceiling,
            "risk_per_trade": governance.controller.risk_per_trade,
            "max_position": governance.controller.max_position,
            "regime_stops": governance.controller.regime_stops,
        },
        "judge": {
            "verdicts_count": len(governance.judge.verdict_history),
        },
        "nvidia_nim": {
            "available": nim.is_available(),
            "model": nim.model,
            "base_url": nim.base_url,
            "models_available": list(NVIDIA_MODELS.keys()),
            "models": {
                "triad": TRIAD_LLM_MODELS,
                "governance": GOVERNANCE_LLM_MODELS,
            },
        },
        "knowledge_repo": repo.get_stats(),
        "okf_structure": OKF_STRUCTURE,
        "rag_memory": rag.get_stats(),
        "prompts": {
            "professor": AGENT_PROMPTS["professor"][:300] + "...",
            "controller": AGENT_PROMPTS["controller"][:300] + "...",
            "judge": AGENT_PROMPTS["judge"][:300] + "...",
        },
    }


@router.get("/analyze/{symbol}")
async def analyze_with_governance(symbol: str, regime_state: int = Query(0, ge=0, le=3)):
    """Análisis completo con el flujo de gobernanza: Tríada → Controlador ↔ Profesor → Juez."""
    try:
        df = download_data(symbol, "2015-01-01")
        if len(df) < 200:
            raise HTTPException(status_code=404, detail=f"Datos insuficientes para {symbol}")

        engine = PredictiveEngine()
        result = engine.analyze(symbol=symbol.upper(), df=df, regime_state=regime_state)

        triad_data = {
            "bull_score": result.triad_consensus.bull_score if result.triad_consensus else 0.0,
            "bear_score": result.triad_consensus.bear_score if result.triad_consensus else 0.0,
            "contrarian_score": result.triad_consensus.contrarian_score if result.triad_consensus else 0.0,
            "triad_score": result.triad_score,
            "triad_recommendation": result.triad_recommendation,
            "triad_agreement": result.triad_agreement,
        }

        governance = GovernanceSystem()
        governance_result = governance.process_governance(
            symbol=symbol.upper(),
            triad_data=triad_data,
            composite_score=result.composite_score,
            regime_state=regime_state,
            current_drawdown=0.0,
            current_exposure=0.0,
            manipulation_risk=result.manipulation_risk,
            macro_score=result.macro_score,
        )

        return {
            "symbol": symbol.upper(),
            "flow": "TRIAD → CONTROLLER ↔ PROFESSOR → JUDGE",
            "predictive": {
                "composite_score": result.composite_score,
                "decision": result.decision,
                "prob_up_short": result.prob_up_short,
                "prob_up_medium": result.prob_up_medium,
                "prob_up_long": result.prob_up_long,
            },
            "governance": governance_result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/record-prediction", dependencies=[Depends(verify_api_key)])
async def record_prediction(agent: str, predicted_up: bool, actual_up: bool, prob: float):
    """Registra una predicción para que el PROFESSOR aprenda."""
    governance = GovernanceSystem()
    governance.professor.record_prediction(agent, predicted_up, actual_up, prob)
    feedback = governance.professor.get_agent_feedback(agent)
    return {
        "recorded": True, "agent": agent,
        "feedback": {
            "accuracy": feedback.accuracy,
            "total_predictions": feedback.total_predictions,
            "recent_trend": feedback.recent_trend,
        },
    }


@router.get("/professor/lessons")
async def get_professor_lessons():
    """Lecciones del PROFESSOR."""
    governance = GovernanceSystem()
    return {
        "lessons": governance.professor.lessons[-20:],
        "teaching_summary": governance.professor.get_teaching_summary(),
    }


@router.get("/professor/feedback")
async def get_agent_feedback():
    """Feedback RAG de todos los agentes."""
    governance = GovernanceSystem()
    return {"agents": [
        {
            "agent": fb.agent, "accuracy": fb.accuracy,
            "total_predictions": fb.total_predictions,
            "correct_predictions": fb.correct_predictions,
            "brier_score": fb.brier_score, "recent_trend": fb.recent_trend,
        }
        for fb in governance.professor.get_all_feedback()
    ]}


@router.get("/knowledge/search")
async def search_knowledge(query: str, domain: str = None, top_k: int = 5):
    """Busca conocimiento en el repositorio RAG/OKF."""
    repo = KnowledgeRepository()
    results = repo.search(query, domain, top_k)
    return {
        "query": query, "domain": domain, "count": len(results),
        "results": [{"id": e.id, "domain": e.domain, "topic": e.topic, "title": e.title,
                      "source": e.source, "year": e.year, "tags": e.tags, "content": e.content} for e in results],
    }


@router.post("/knowledge/add", dependencies=[Depends(verify_api_key)])
async def add_knowledge(domain: str, topic: str, title: str, content: str, source: str,
                        year: int = 0, tags: str = ""):
    """Agrega una entrada al repositorio de conocimiento."""
    repo = KnowledgeRepository()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    entry = repo.add_entry(domain, topic, title, content, source, year, tag_list)
    return {"added": True, "id": entry.id, "stats": repo.get_stats()}


@router.get("/prompts")
async def get_prompts():
    """Prompts nivel dios de cada agente."""
    return {
        "professor": PROFESSOR_PROMPT,
        "controller": CONTROLLER_PROMPT,
        "judge": JUDGE_PROMPT,
    }
