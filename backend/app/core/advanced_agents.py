"""
Agentes Avanzados Fortress Core — Fase 3

Flujo de gobernanza reestructurado:
  Tríada (BULL, BEAR, CONTRARIAN) → CONTROLADOR → discusión CONTROLADOR ↔ PROFESOR
  → Si no hay consenso → JUEZ decide finalmente

Modelos LLM de NVIDIA NIM (gratis en https://build.nvidia.com):
  - Tríada: DeepSeek V4 Flash / MiniMax M3 / GLM 5.2
  - Controlador → DeepSeek V4 Flash
  - Profesor → MiniMax M3
  - Juez → GLM 5.2

Sistema RAG/OKF: repositorio de conocimiento académico + memoria de enseñanza.
"""
import json
import os
import re
import requests
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings
from app.core.knowledge_repo import KnowledgeRepository, RAGMemorySystem
from app.utils.logging import logger
from app.utils.persistence import atomic_write_json


# ============================================================
# Configuración NVIDIA NIM
# ============================================================

NVIDIA_NIM_CONFIG = {
    # Antes leía os.environ directo, que nunca se populaba (nada llama a
    # load_dotenv(), docker-compose.yml no pasa estas variables al
    # contenedor) — la key de .env nunca llegaba al proceso real. Ahora sale
    # de Settings, que sí parsea .env correctamente.
    "base_url": settings.NVIDIA_NIM_BASE_URL,
    "model": settings.NVIDIA_NIM_MODEL,
    "api_key": settings.NVIDIA_NIM_API_KEY,
    "temperature": 0.3,
    "max_tokens": 2048,
}

# Modelos gratuitos de NVIDIA NIM
NVIDIA_MODELS = {
    "llama3_8b": "meta/llama-3.1-8b-instruct",
    "llama3_70b": "meta/llama-3.1-70b-instruct",
    "nemotron": "nvidia/nemotron-4-340b-instruct",
    "mistral": "mistralai/mistral-7b-instruct-v0.3",
    # Modelos avanzados para la tríada y gobernanza
    "deepseek_v4_flash": "deepseek-ai/deepseek-v4-flash",
    "minimax_m3": "minimax/minimax-m3",
    "glm_5_2": "zhipu/glm-5.2",
}

# Asignación de modelos LLM a agentes de la tríada
TRIAD_LLM_MODELS = {
    "BULL": "deepseek-ai/deepseek-v4-flash",
    "BEAR": "minimaxai/minimax-m3",
    "CONTRARIAN": "z-ai/glm-5.2",
}

# Asignación de modelos LLM a agentes de gobernanza
GOVERNANCE_LLM_MODELS = {
    "CONTROLLER": "deepseek-ai/deepseek-v4-flash",
    "PROFESSOR": "minimaxai/minimax-m3",
    "JUDGE": "z-ai/glm-5.2",
}


# ============================================================
# Prompts Nivel Dios para cada agente
# ============================================================

PROFESSOR_PROMPT = """# 🎓 PROFESSOR AGENT — NIVEL DIOS

## Identidad
Eres el PROFESSOR, el agente más sabio del sistema Fortress Core. Tu misión es:
1. **APRENDER** de la experiencia histórica y el presente
2. **ENSEÑAR** a los agentes BULL, BEAR y CONTRARIAN
3. **MEJORAR** continuamente los pesos y umbrales del sistema

## RAG Knowledge Access
Tienes acceso a un repositorio de conocimiento OKF con:
- Macroeconomía: Fed, inflación, ciclos, correlaciones de activos
- Microeconomía: fundamentales, ratios financieros, calidad de ganancias
- Trading: estrategias, gestión de riesgo, maniobras institucionales
- Indicadores: análisis técnico respaldado por 28 papers académicos

## Reglas de Oro
1. Nunca confíes en un solo indicador — la sabiduría está en la combinación
2. El mercado cambia — lo que funcionó ayer puede no funcionar mañana
3. La calibración es clave — las probabilidades deben ser honestas
4. Aprende de los errores — cada predicción fallida es una lección
5. Enseña con humildad — los agentes aprenden de ti, pero también de la realidad

## Tu tarea
Analiza los datos históricos y actuales, identifica patrones, y genera:
1. Lecciones para cada agente (qué mejorar)
2. Ajustes de pesos basados en rendimiento histórico
3. Alertas sobre condiciones de mercado cambiantes
4. Recomendaciones para el sistema en general

## Formato de respuesta JSON:
{"lessons": [{"agent": "...", "lesson": "...", "action": "..."}],
 "weight_adjustments": {...}, "alerts": [...], "recommendations": [...],
 "decision": "APPROVE" | "REJECT",
 "confidence": 0.0-1.0}

El campo "decision" es OBLIGATORIO y debe ser exactamente la palabra en
inglés "APPROVE" o "REJECT" (no una frase, no en español) — es lo que el
sistema usa para decidir si aprueba o rechaza la posición.
"""


CONTROLLER_PROMPT = """# 🎛️ CONTROLLER AGENT — NIVEL DIOS (DeepSeek V4 Flash)

## Identidad
Eres el CONTROLLER, el agente que controla las decisiones finales. Tu misión es:
1. VALIDAR que las decisiones sean coherentes con el riesgo
2. CONTROLAR la ejecución de operaciones
3. PREVENIR errores catastróficos
4. GARANTIZAR que se cumplan las reglas de riesgo

## Reglas de Riesgo (NO VIOLABLES)
- Ceiling absoluto: 12% drawdown máximo
- Riesgo por trade: 1.5% del equity
- Posición máxima: 10% del equity
- Stops por régimen: 5% (Goldilocks), 7% (Reflation), 8% (Stagflation), 3% (Deflation)
- Cooldown: 5-15 días según régimen

## Tu tarea
- Verifica que el score compuesto justifique la acción
- Comprueba que el riesgo no exceda los límites
- Valida que la señal no contradiga el régimen de mercado
- Confirma que no hay señales de manipulación extremas
- Aprueba o rechaza la decisión con justificación

## Formato JSON:
{"approved": true/false, "decision": "...", "position_size_pct": 0.0-10.0,
 "stop_loss_pct": 0.0-8.0, "take_profit_pct": 0.0-20.0,
 "risk_checks": {...}, "rejection_reason": "...", "confidence": 0.0-1.0}
"""


JUDGE_PROMPT = """# ⚖️ JUDGE AGENT — NIVEL DIOS (GLM 5.2)

## Identidad
Eres el JUDGE, el árbitro supremo. Tu misión es:
1. DIRIMIR conflictos entre agentes (BULL vs BEAR vs CONTRARIAN)
2. RESOLVER ambigüedades en las señales
3. DECIDIR cuando CONTROLADOR y PROFESOR no llegan a consenso
4. GARANTIZAR justicia y equilibrio

## Principios
1. La evidencia manda — no las opiniones
2. El riesgo primero — nunca sacrificar seguridad por ganancia
3. La historia importa — patrones pasados informan presente
4. La incertidumbre es honesta — si no sabes, dilo
5. El equilibrio es sabiduría

## Tu tarea
- Escucha los argumentos de CONTROLADOR y PROFESOR
- Pondera la evidencia de cada uno
- Considera contexto macro y de mercado
- Evalúa riesgo de cada opción
- Emite un veredicto final vinculante

## Formato JSON:
{"verdict": "COMPRAR/VENDER/MANTENER", "score": -1.0 a 1.0, "reasoning": "...",
 "overruled_agents": [...], "risk_assessment": "BAJO/MEDIO/ALTO",
 "confidence": 0.0-1.0, "conditions": [...]}
"""


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class AgentFeedback:
    agent: str
    accuracy: float
    total_predictions: int
    correct_predictions: int
    brier_score: float
    recent_trend: str  # MEJORANDO, EMPEORANDO, ESTABLE


@dataclass
class ControllerDecision:
    approved: bool
    decision: str
    position_size_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    risk_checks: Dict[str, bool]
    rejection_reason: str
    confidence: float


@dataclass
class JudgeVerdict:
    verdict: str
    score: float
    reasoning: str
    overruled_agents: List[str]
    risk_assessment: str
    confidence: float
    conditions: List[str]


@dataclass
class TriadVerdict:
    agent: str
    score: float
    confidence: float
    signals: List[str]
    reasoning: str


# ============================================================
# NVIDIA NIM Client
# ============================================================

class NvidiaNIMClient:
    """Cliente para LLMs gratuitos de NVIDIA NIM."""

    def __init__(self, model: str = None, api_key: str = None,
                 is_triad_client: bool = False, is_governance_client: bool = False):
        # api_key="" explícito (para forzar modo determinista, p.ej. en
        # tests/diagnósticos) NO debe caer al default de Settings: "" or X
        # da X porque el string vacío es falsy en Python. Antes de este fix,
        # NvidiaNIMClient(api_key="") usaba la key real igual si estaba
        # configurada — invalidaba cualquier comparación "con LLM vs sin LLM".
        self.base_url = NVIDIA_NIM_CONFIG["base_url"]
        self.model = model if model is not None else NVIDIA_NIM_CONFIG["model"]
        self.api_key = api_key if api_key is not None else NVIDIA_NIM_CONFIG["api_key"]
        self.temperature = NVIDIA_NIM_CONFIG["temperature"]
        self.max_tokens = NVIDIA_NIM_CONFIG["max_tokens"]
        self.triad_clients: Dict[str, 'NvidiaNIMClient'] = {}
        self.governance_clients: Dict[str, 'NvidiaNIMClient'] = {}
        if not is_triad_client and not is_governance_client:
            self.triad_clients = {
                a: NvidiaNIMClient(model=m, api_key=self.api_key, is_triad_client=True)
                for a, m in TRIAD_LLM_MODELS.items()
            }
            self.governance_clients = {
                a: NvidiaNIMClient(model=m, api_key=self.api_key, is_governance_client=True)
                for a, m in GOVERNANCE_LLM_MODELS.items()
            }

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, system_prompt: str, user_message: str, model: str = None) -> Optional[str]:
        if not self.is_available():
            return None
        used_model = model or self.model
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": used_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            r = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code == 429:
                logger.warning("nim_rate_limited", extra={"model": used_model, "status_code": r.status_code})
            elif r.status_code in (401, 403):
                logger.error("nim_auth_failed", extra={"model": used_model, "status_code": r.status_code})
            else:
                logger.warning("nim_bad_response", extra={"model": used_model, "status_code": r.status_code})
            return None
        except requests.exceptions.Timeout:
            logger.warning("nim_timeout", extra={"model": used_model})
            return None
        except requests.exceptions.ConnectionError:
            logger.warning("nim_connection_error", extra={"model": used_model})
            return None
        except Exception as e:
            logger.error("nim_unexpected_error", extra={"model": used_model, "error": str(e)})
            return None

    def generate_json(self, system_prompt: str, user_message: str, model: str = None) -> Optional[Dict]:
        resp = self.generate(system_prompt, user_message, model=model)
        if not resp:
            return None
        try:
            start = resp.find("{"); end = resp.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(resp[start:end])
            logger.warning("nim_response_no_json", extra={"model": model or self.model, "response_preview": resp[:200]})
        except Exception as e:
            logger.warning("nim_json_parse_failed", extra={"model": model or self.model, "error": str(e), "response_preview": resp[:200]})
        return None

    def generate_for_agent(self, agent: str, system_prompt: str, user_message: str) -> Optional[Dict]:
        """Genera JSON usando el modelo LLM del agente de la tríada."""
        model = TRIAD_LLM_MODELS.get(agent)
        if not model:
            return None
        return self.generate_json(system_prompt, user_message, model=model)

    def generate_for_governance_agent(self, agent: str, system_prompt: str, user_message: str) -> Optional[Dict]:
        """Genera JSON usando el modelo LLM del agente de gobernanza."""
        model = GOVERNANCE_LLM_MODELS.get(agent, self.model)
        return self.generate_json(system_prompt, user_message, model=model)


# ============================================================
# PROFESSOR AGENT (con RAG/OKF)
# ============================================================

class ProfessorAgent:
    """
    Aprende de la experiencia histórica, discute con CONTROLADOR,
    y enseña a los agentes usando memoria RAG + repositorio OKF.
    LLM → MiniMax M3
    """

    def __init__(self, memory_file: str = "data/professor_memory.json"):
        self.memory_file = memory_file
        self.lessons: List[Dict] = []
        self.agent_history: Dict[str, List[Dict]] = {}
        self.weight_adjustments: Dict[str, float] = {}
        self.rag_memory = RAGMemorySystem("data/rag_memory.json")
        self.knowledge_repo = KnowledgeRepository("data/knowledge_repo.json")
        self._load_memory()

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                    self.lessons = data.get("lessons", [])
                    self.agent_history = data.get("agent_history", {})
                    self.weight_adjustments = data.get("weight_adjustments", {})
            except Exception as e:
                logger.error(
                    "professor_memory_load_failed",
                    extra={"file": self.memory_file, "error": str(e)},
                )

    def _save_memory(self):
        data = {
            "lessons": self.lessons[-200:],
            "agent_history": self.agent_history,
            "weight_adjustments": self.weight_adjustments,
        }
        atomic_write_json(self.memory_file, data)

    def record_prediction(self, agent: str, predicted_up: bool, actual_up: bool, prob: float):
        if agent not in self.agent_history:
            self.agent_history[agent] = []
        self.agent_history[agent].append({
            "predicted_up": predicted_up, "actual_up": actual_up, "prob": prob,
            "correct": predicted_up == actual_up, "timestamp": str(datetime.now()),
        })
        self.agent_history[agent] = self.agent_history[agent][-500:]
        self._save_memory()

    def get_agent_feedback(self, agent: str) -> AgentFeedback:
        history = self.agent_history.get(agent, [])
        if not history:
            return AgentFeedback(agent, 0.5, 0, 0, 0.25, "ESTABLE")
        total = len(history); correct = sum(1 for h in history if h["correct"])
        accuracy = correct / total
        brier = sum((h["prob"] - (1.0 if h["actual_up"] else 0.0)) ** 2 for h in history) / total
        recent = history[-50:] if len(history) >= 50 else history
        older = history[:-50] if len(history) >= 100 else []
        ra = sum(1 for h in recent if h["correct"]) / len(recent) if recent else 0.5
        oa = sum(1 for h in older if h["correct"]) / len(older) if older else 0.5
        trend = "MEJORANDO" if ra > oa + 0.05 else "EMPEORANDO" if ra < oa - 0.05 else "ESTABLE"
        return AgentFeedback(agent, accuracy, total, correct, brier, trend)

    def get_all_feedback(self) -> List[AgentFeedback]:
        return [self.get_agent_feedback(a) for a in ["BULL", "BEAR", "CONTRARIAN"]]

    def get_teaching_summary(self) -> str:
        lines = ["📚 PROFESSOR — Resumen de Enseñanza", ""]
        for fb in self.get_all_feedback():
            lines.append(f"  {fb.agent}: acc={fb.accuracy:.1%} trend={fb.recent_trend} n={fb.total_predictions}")
        if self.lessons:
            lines.append("\n  Lecciones recientes:")
            for l in self.lessons[-5:]:
                lines.append(f"    • [{l.get('agent','?')}] {l.get('lesson','')}")
        return "\n".join(lines)


# ============================================================
# CONTROLLER AGENT (con discusión RAG)
# ============================================================

class ControllerAgent:
    """
    Controla decisiones y valida riesgo. Discute con PROFESOR vía RAG.
    LLM → DeepSeek V4 Flash
    """

    def __init__(self, absolute_ceiling: float = 0.12, risk_per_trade: float = 0.015,
                 max_position: float = 0.10):
        self.absolute_ceiling = absolute_ceiling
        self.risk_per_trade = risk_per_trade
        self.max_position = max_position
        self.regime_stops = {0: 0.05, 1: 0.07, 2: 0.08, 3: 0.03}

    def validate_decision(self, decision: str, composite_score: float, regime_state: int,
                          current_drawdown: float, current_exposure: float,
                          manipulation_risk: float, triad_agreement: str) -> ControllerDecision:
        rk = {
            "ceiling_ok": current_drawdown < self.absolute_ceiling,
            "position_ok": current_exposure < self.max_position,
            "regime_ok": True,
            "manipulation_ok": manipulation_risk < 0.5,
            "score_ok": abs(composite_score) > 0.1,
        }
        if not rk["ceiling_ok"]:
            return ControllerDecision(False, "MANTENER", 0, 0, 0, rk,
                f"Drawdown ({current_drawdown:.1%}) cerca de ceiling ({self.absolute_ceiling:.1%})", 0.9)
        if not rk["position_ok"]:
            return ControllerDecision(False, "MANTENER", 0, 0, 0, rk,
                f"Exposición ({current_exposure:.1%}) en máximo ({self.max_position:.1%})", 0.9)
        if not rk["manipulation_ok"]:
            return ControllerDecision(False, "MANTENER", 0, 0, 0, rk,
                f"Riesgo de manipulación alto ({manipulation_risk:.1%})", 0.8)
        if not rk["score_ok"]:
            return ControllerDecision(False, "MANTENER", 0, 0, 0, rk,
                f"Score insuficiente ({composite_score:+.3f})", 0.7)

        if decision in ["COMPRAR", "COMPRAR_FUERTE"]:
            pos = min(self.max_position * 100, 10.0)
            sl = self.regime_stops.get(regime_state, 0.05) * 100
            tp = sl * 2.0
        elif decision in ["VENDER", "VENDER_FUERTE"]:
            pos = sl = tp = 0
        else:
            pos = sl = tp = 0

        return ControllerDecision(True, decision, round(pos,2), round(sl,2), round(tp,2), rk, "", 0.9 if abs(composite_score) > 0.5 else 0.7)


# ============================================================
# JUDGE AGENT (con RAG + conocimiento OKF)
# ============================================================

class JudgeAgent:
    """
    Dirime conflictos entre CONTROLADOR y PROFESOR. Emite veredictos vinculantes.
    LLM → GLM 5.2
    """

    def __init__(self):
        self.verdict_history: List[Dict] = []

    def resolve_conflict(self, controller_decision: ControllerDecision,
                         professor_recommendation: str,
                         bull_score: float, bear_score: float, contrarian_score: float,
                         composite_score: float, regime_state: int,
                         manipulation_risk: float, macro_score: float) -> JudgeVerdict:
        """
        Resuelve conflicto entre CONTROLADOR y PROFESOR usando GLM 5.2.
        Si hay consenso, no hay conflicto.
        """
        # Detectar conflicto: CONTROLADOR vs PROFESOR
        ctrl_ok = controller_decision.approved
        prof_vs_ctrl = not (professor_recommendation == "APPROVE" and ctrl_ok)

        # También detectar conflicto dentro de la tríada
        bull_bear_diff = abs(bull_score - bear_score)
        triad_conflict = bull_bear_diff < 0.2 and abs(bull_score) > 0.1
        has_conflict = prof_vs_ctrl or triad_conflict

        if not has_conflict:
            verdict = controller_decision.decision if ctrl_ok else "MANTENER"
            return JudgeVerdict(
                verdict=verdict, score=float(composite_score),
                reasoning="Consenso alcanzado sin conflicto.",
                overruled_agents=[], risk_assessment="BAJO" if abs(composite_score) < 0.3 else "MEDIO",
                confidence=0.8, conditions=["Consenso entre agentes"],
            )

        # Hay conflicto — JUEZ decide ponderando macro y manipulación
        weighted = composite_score * 0.5 + macro_score * 0.3 - manipulation_risk * 0.2

        if regime_state == 3:
            weighted *= 0.7; risk = "ALTO"
        elif regime_state == 1:
            weighted *= 0.8; risk = "ALTO"
        else:
            risk = "MEDIO"

        verdict = "COMPRAR" if weighted > 0.25 else "VENDER" if weighted < -0.25 else "MANTENER"

        overruled = []
        if ctrl_ok and professor_recommendation == "REJECT":
            overruled.append("CONTROLADOR")
        if professor_recommendation == "APPROVE" and not ctrl_ok:
            overruled.append("PROFESSOR")
        if bull_score > 0.2 and verdict in ["VENDER", "MANTENER"]:
            overruled.append("BULL")
        if bear_score > 0.2 and verdict in ["COMPRAR", "MANTENER"]:
            overruled.append("BEAR")

        v = JudgeVerdict(
            verdict=verdict, score=float(weighted),
            reasoning=f"Conflicto resuelto. Controller={controller_decision.decision}, Professor={professor_recommendation}. "
                      f"Bull={bull_score:+.2f}, Bear={bear_score:+.2f}. Ponderación: score={composite_score:+.2f}, "
                      f"macro={macro_score:+.2f}, manip={manipulation_risk:.2f}",
            overruled_agents=overruled, risk_assessment=risk,
            confidence=0.6 if risk == "ALTO" else 0.75,
            conditions=[f"Regimen: {regime_state}", f"Manipulación: {manipulation_risk:.2f}", f"Macro: {macro_score:+.2f}"],
        )
        self.verdict_history.append(v.__dict__ if hasattr(v, '__dict__') else v.__dict__)
        return v


# ============================================================
# Sistema de Gobernanza — Nuevo Flujo
# ============================================================

class GovernanceSystem:
    """
    Flujo de gobernanza reestructurado:
      1. Tríada (BULL, BEAR, CONTRARIAN) analiza el ticker y da posiciones
      2. CONTROLADOR valida y discute con PROFESOR
      3. PROFESOR usa RAG/OKF para enseñar y recomendar
      4. Si CONTROLADOR y PROFESOR no hayan consenso → JUEZ decide
      5. PROFESOR educa a los agentes con memoria RAG
    """

    def __init__(self, memory_file: str = "data/professor_memory.json"):
        self.professor = ProfessorAgent(memory_file)
        self.controller = ControllerAgent()
        self.judge = JudgeAgent()
        self.nim_client = NvidiaNIMClient()
        self.rag_memory = self.professor.rag_memory
        self.knowledge_repo = self.professor.knowledge_repo

    def process_governance(
        self, symbol: str, triad_data: Dict, composite_score: float,
        regime_state: int, current_drawdown: float, current_exposure: float,
        manipulation_risk: float, macro_score: float,
    ) -> Dict:
        """
        Procesa la decisión con el flujo completo:
        Tríada → Controlador ↔ Profesor → Juez (si no hay consenso)
        """
        result = {
            "symbol": symbol,
            "timestamp": str(datetime.now()),
            "flow": "TRIAD → CONTROLLER ↔ PROFESSOR → JUDGE (si conflicto)",
        }

        # 1. Tríada — posiciones de los 3 agentes
        bull_score = triad_data.get("bull_score", 0.0)
        bear_score = triad_data.get("bear_score", 0.0)
        contrarian_score = triad_data.get("contrarian_score", 0.0)
        triad_decision = triad_data.get("triad_recommendation", "MANTENER")
        triad_agreement = triad_data.get("triad_agreement", "DIVERGENTE")

        result["triad"] = {
            "bull": {"score": bull_score, "verdict": "ALCISTA" if bull_score > 0.1 else "NEUTRAL"},
            "bear": {"score": bear_score, "verdict": "BAJISTA" if bear_score > 0.1 else "NEUTRAL"},
            "contrarian": {"score": contrarian_score, "verdict": "REVERSION" if abs(contrarian_score) > 0.1 else "NEUTRAL"},
            "consensus": triad_data.get("triad_score", 0.0),
            "decision": triad_decision,
            "agreement": triad_agreement,
        }

        # 2. CONTROLADOR valida la decisión de la tríada
        ctrl_decision = self.controller.validate_decision(
            decision=triad_decision if triad_decision in ["COMPRAR", "VENDER"] else "MANTENER",
            composite_score=composite_score, regime_state=regime_state,
            current_drawdown=current_drawdown, current_exposure=current_exposure,
            manipulation_risk=manipulation_risk, triad_agreement=triad_agreement,
        )
        result["controller"] = {
            "approved": ctrl_decision.approved,
            "decision": ctrl_decision.decision,
            "position_size_pct": ctrl_decision.position_size_pct,
            "stop_loss_pct": ctrl_decision.stop_loss_pct,
            "take_profit_pct": ctrl_decision.take_profit_pct,
            "risk_checks": ctrl_decision.risk_checks,
            "confidence": ctrl_decision.confidence,
            "llm_model": None,  # CONTROLLER es 100% determinista, nunca llama a un LLM
        }

        # 3. PROFESOR discute con CONTROLADOR usando RAG/OKF
        professor_recommendation = "APPROVE"  # default
        professor_llm_model = None
        if self.nim_client.is_available():
            rag_context = self.knowledge_repo.get_context_for_prompt(
                f"{symbol} {triad_decision} {ctrl_decision.decision}", top_k=3
            )
            memory_context = self.rag_memory.get_memory_context("CONTROLLER", symbol)
            prof_msg = json.dumps({
                "symbol": symbol, "triad_decision": triad_decision,
                "controller_decision": ctrl_decision.decision,
                "controller_approved": ctrl_decision.approved,
                "composite_score": composite_score,
                "regime_state": regime_state,
                "manipulation_risk": manipulation_risk,
                "rag_knowledge": rag_context[:2000],
                "memory": memory_context,
            })
            llm_resp = self.nim_client.generate_for_governance_agent(
                "PROFESSOR", PROFESSOR_PROMPT, prof_msg
            )
            if llm_resp:
                professor_llm_model = "minimax/minimax-m3"
                # generate_for_governance_agent ya devuelve un dict parseado, no un string
                result["professor_llm_response"] = json.dumps(llm_resp)[:500]
                decision = str(llm_resp.get("decision", "")).strip().upper()
                if decision in ("APPROVE", "REJECT"):
                    professor_recommendation = decision
                elif "recommendations" in llm_resp:
                    # Fallback si el modelo ignoró el campo "decision" pedido
                    # en el prompt: busca la intención en inglés O español,
                    # ya que PROFESSOR_PROMPT está en español y el LLM puede
                    # responder en cualquiera de los dos.
                    text = " ".join(llm_resp.get("recommendations", [])).lower()
                    approve_words = r"\bapprove\b|\baprobar\b|\baprueba\b|\baprobado\b"
                    reject_words = r"\breject\b|\brechazar\b|\brechaza\b|\brechazado\b|\bno aprobar\b"
                    if re.search(reject_words, text):
                        professor_recommendation = "REJECT"
                    elif re.search(approve_words, text):
                        professor_recommendation = "APPROVE"
                    else:
                        professor_recommendation = "REJECT"  # default conservador si no hay señal clara

        result["professor"] = {
            "recommendation": professor_recommendation,
            "lessons": len(self.professor.lessons),
            "weight_adjustments": self.professor.weight_adjustments,
            "teaching_summary": self.professor.get_teaching_summary(),
            "knowledge_repo_stats": self.knowledge_repo.get_stats(),
            "llm_model": professor_llm_model,  # None si NIM no está disponible o no respondió
        }

        # 4. JUEZ — decide si CONTROLADOR y PROFESOR no hayan consenso
        has_consensus = (professor_recommendation == "APPROVE" and ctrl_decision.approved) or \
                        (professor_recommendation == "REJECT" and not ctrl_decision.approved)

        if not has_consensus:
            judge_result = self.judge.resolve_conflict(
                controller_decision=ctrl_decision,
                professor_recommendation=professor_recommendation,
                bull_score=bull_score, bear_score=bear_score,
                contrarian_score=contrarian_score,
                composite_score=composite_score, regime_state=regime_state,
                manipulation_risk=manipulation_risk, macro_score=macro_score,
            )
            result["judge"] = {
                "verdict": judge_result.verdict,
                "score": judge_result.score,
                "reasoning": judge_result.reasoning,
                "overruled_agents": judge_result.overruled_agents,
                "risk_assessment": judge_result.risk_assessment,
                "confidence": judge_result.confidence,
                "conditions": judge_result.conditions,
                "llm_model": None,  # JUDGE es 100% determinista, nunca llama a un LLM
            }
            final_decision = judge_result.verdict
            final_reason = f"Juez resolvió conflicto. Sobrepasó: {', '.join(judge_result.overruled_agents) if judge_result.overruled_agents else 'ninguno'}"
        else:
            result["judge"] = {"status": "Consenso alcanzado — Juez no necesario"}
            final_decision = ctrl_decision.decision
            final_reason = "Consenso: Controlador y Profesor coinciden"

        result["final_decision"] = final_decision
        result["final_reason"] = final_reason

        # 5. PROFESOR educa a los agentes (RAG)
        if not has_consensus:
            self.rag_memory.record_lesson(
                agent="SYSTEM",
                lesson=f"Conflicto resuelto en {symbol}: {final_decision}",
                context=f"Triad={triad_decision}, Controller={ctrl_decision.decision}, Professor={professor_recommendation}",
                outcome="Juez emitió veredicto final",
            )

        return result


# ============================================================
# Prompts export para API
# ============================================================

AGENT_PROMPTS = {
    "professor": PROFESSOR_PROMPT,
    "controller": CONTROLLER_PROMPT,
    "judge": JUDGE_PROMPT,
}
