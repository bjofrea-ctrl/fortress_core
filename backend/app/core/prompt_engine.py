"""
Prompt Engine Nivel Dios — Fortress Core Fase 4

Sistema de ingeniería de prompts avanzada con:
1. Context Engineering — RAG + memoria + datos en vivo
2. Memory Engineering — memoria a corto y largo plazo
3. Hardiness Checks — validación de respuestas LLM
4. Chain-of-Thought — razonamiento estructurado
5. Self-Consistency — múltiples muestras y votación
6. Few-Shot Learning — ejemplos de alta calidad
7. Structured Output — JSON schema estricto
8. Adversarial Testing — detección de alucinaciones

Referencias:
- Wei et al. (2022): Chain-of-Thought Prompting
- Wang et al. (2022): Self-Consistency
- Brown et al. (2020): Few-Shot Learning
- Lewis et al. (2020): RAG
- Schulman (2023): Prompt Engineering Best Practices
- Anthropic (2024): Claude Prompt Engineering
"""
import json
import os
import re
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from app.utils.logging import logger
from app.utils.persistence import atomic_write_json


# ============================================================
# 1. Memory System — Memoria Contextual
# ============================================================

@dataclass
class MemoryItem:
    """Item de memoria con metadata."""
    content: str
    category: str  # "lesson", "pattern", "fact", "warning", "success"
    timestamp: str
    importance: float  # 0-1
    tags: List[str] = field(default_factory=list)
    source: str = "system"


class MemorySystem:
    """
    Sistema de memoria jerárquica:
    - Memoria de trabajo (working): contexto inmediato
    - Memoria a corto plazo (short): últimas 100 interacciones
    - Memoria a largo plazo (long): conocimiento persistente
    """

    def __init__(self, memory_file: str = "data/prompt_memory.json"):
        self.memory_file = memory_file
        self.working_memory: List[MemoryItem] = []
        self.short_term: List[MemoryItem] = []
        self.long_term: List[MemoryItem] = []
        self._load()

    def _load(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                self.short_term = [MemoryItem(**i) for i in data.get("short_term", [])]
                self.long_term = [MemoryItem(**i) for i in data.get("long_term", [])]
            except Exception as e:
                logger.error("prompt_memory_load_failed", extra={"file": self.memory_file, "error": str(e)})

    def _save(self):
        data = {
            "short_term": [i.__dict__ for i in self.short_term[-100:]],
            "long_term": [i.__dict__ for i in self.long_term[-500:]],
        }
        atomic_write_json(self.memory_file, data)

    def add(self, content: str, category: str = "fact", importance: float = 0.5,
            tags: List[str] = None, source: str = "system"):
        """Agrega un item a memoria."""
        item = MemoryItem(
            content=content,
            category=category,
            timestamp=str(datetime.now()),
            importance=importance,
            tags=tags or [],
            source=source,
        )
        self.short_term.append(item)
        # Promover a largo plazo si es importante
        if importance > 0.7:
            self.long_term.append(item)
        self._save()

    def retrieve(self, query: str, top_k: int = 5, category: Optional[str] = None) -> List[MemoryItem]:
        """Recupera memoria relevante por similitud de tokens."""
        query_tokens = set(re.findall(r'\w+', query.lower()))
        if not query_tokens:
            return []

        all_items = self.long_term + self.short_term[-50:]
        scored = []
        for item in all_items:
            if category and item.category != category:
                continue
            item_tokens = set(re.findall(r'\w+', item.content.lower()))
            inter = len(query_tokens & item_tokens)
            union = len(query_tokens | item_tokens)
            jaccard = inter / union if union > 0 else 0
            # Ponderar por importancia
            score = jaccard * item.importance
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for s, item in scored[:top_k] if s > 0]

    def get_context(self, query: str, top_k: int = 3) -> str:
        """Genera contexto de memoria para prompts."""
        items = self.retrieve(query, top_k)
        if not items:
            return ""
        lines = ["[MEMORIA RELEVANTE]"]
        for item in items:
            lines.append(f"- [{item.category}] {item.content}")
        return "\n".join(lines)

    def get_stats(self) -> Dict:
        return {
            "short_term": len(self.short_term),
            "long_term": len(self.long_term),
            "categories": {c: sum(1 for i in self.long_term if i.category == c)
                          for c in set(i.category for i in self.long_term)},
        }


# ============================================================
# 2. Hardiness Checks — Validación de Respuestas
# ============================================================

class HardinessChecker:
    """
    Sistema de validación de respuestas LLM:
    1. Schema validation — JSON válido con campos requeridos
    2. Range validation — scores dentro de rangos esperados
    3. Consistency validation — no contradice datos deterministas
    4. Hallucination detection — detecta números inventados
    5. Confidence calibration — confianza coherente con score
    """

    REQUIRED_FIELDS = {
        "score": (float, lambda x: -1.0 <= x <= 1.0),
        "confidence": (float, lambda x: 0.0 <= x <= 1.0),
        "reasoning": (str, lambda x: len(x) > 10),
    }

    @staticmethod
    def validate_fields(data: Dict) -> List[str]:
        """Valida un dict ya parseado contra REQUIRED_FIELDS (tipo + rango)."""
        errors = []
        for field_name, (field_type, validator) in HardinessChecker.REQUIRED_FIELDS.items():
            if field_name not in data:
                errors.append(f"Campo requerido faltante: {field_name}")
                continue
            value = data[field_name]
            if not isinstance(value, field_type):
                errors.append(f"Campo {field_name} tiene tipo incorrecto: {type(value).__name__}")
                continue
            if not validator(value):
                errors.append(f"Campo {field_name} fuera de rango: {value}")
        return errors

    @staticmethod
    def validate_json_response(response: str) -> Tuple[Optional[Dict], List[str]]:
        """Valida que la respuesta sea JSON válido con campos requeridos."""
        try:
            # Extraer JSON del texto
            start = response.find("{")
            end = response.rfind("}") + 1
            if start < 0 or end <= start:
                return None, ["No se encontró JSON en la respuesta"]

            data = json.loads(response[start:end])
        except json.JSONDecodeError as e:
            return None, [f"JSON inválido: {str(e)}"]

        errors = HardinessChecker.validate_fields(data)
        return data if not errors else None, errors

    @staticmethod
    def validate_against_deterministic(llm_score: float, deterministic_score: float,
                                       max_deviation: float = 0.5) -> Tuple[bool, str]:
        """
        Valida que el score LLM no se desvíe demasiado del determinista.
        Si el LLM se desvía mucho, probablemente está alucinando.
        """
        deviation = abs(llm_score - deterministic_score)
        if deviation > max_deviation:
            return False, f"Desviación excesiva: LLM={llm_score:+.3f} vs determinista={deterministic_score:+.3f}"
        return True, f"Desviación aceptable: {deviation:.3f}"

    @staticmethod
    def validate_confidence_consistency(score: float, confidence: float) -> Tuple[bool, str]:
        """
        Valida que la confianza sea coherente con la magnitud del score.
        Un score cercano a 0 con confianza alta es sospechoso.
        """
        if abs(score) < 0.1 and confidence > 0.8:
            return False, f"Confianza alta ({confidence:.2f}) con score neutral ({score:+.3f})"
        if abs(score) > 0.7 and confidence < 0.3:
            return False, f"Confianza baja ({confidence:.2f}) con score extremo ({score:+.3f})"
        return True, ""

    @staticmethod
    def detect_hallucination(text: str, known_values: Dict[str, float]) -> List[str]:
        """Detecta números en el texto que no coinciden con datos conocidos."""
        hallucinations = []
        for key, known_value in known_values.items():
            # Buscar el número cerca de la clave
            pattern = rf"{key}[\s:=]+([-+]?\d+\.?\d*)"
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    val = float(m)
                    if known_value and abs(val - known_value) / max(abs(known_value), 1) > 0.2:
                        hallucinations.append(
                            f"Posible alucinación: {key}={val} vs real={known_value:.2f}"
                        )
                except ValueError:
                    pass
        return hallucinations


# ============================================================
# 3. Chain-of-Thought Templates
# ============================================================

COT_TEMPLATES = {
    "analysis": """Analiza paso a paso:

PASO 1: Datos disponibles
- Precio: {price}
- RSI: {rsi}
- EMA20/50/200: {ema20}/{ema50}/{ema200}
- ADX: {adx}
- MACD: {macd}
- Volumen ratio: {volume_ratio}

PASO 2: Identifica la tendencia
- ¿Está el precio sobre o bajo las EMAs?
- ¿La tendencia es fuerte (ADX > 25) o débil?

PASO 3: Identifica momentum
- ¿RSI está en zona de sobrecompra/sobreventa?
- ¿MACD confirma la dirección?

PASO 4: Identifica volumen y flujo
- ¿El volumen confirma el movimiento?
- ¿CMF indica acumulación o distribución?

PASO 5: Considera el contexto macro
- ¿Risk-on o risk-off?
- ¿Hay señales de manipulación?

PASO 6: Conclusión
- Score final en [-1, +1]
- Confianza en [0, 1]
- Razonamiento completo""",

    "BEAR": """Analiza los riesgos paso a paso:

PASO 1: Identifica debilidades de tendencia
- ¿EMA20 < EMA50 < EMA200?
- ¿Precio bajo la nube de Ichimoku?

PASO 2: Identifica sobrecompra
- ¿RSI > 70?
- ¿Precio sobre banda superior de Bollinger?

PASO 3: Identifica distribución
- ¿CMF negativo?
- ¿Volumen decreciente en subidas?
- ¿Divergencias RSI/precio?

PASO 4: Fundamentales débiles
- ¿P/E elevado?
- ¿Deuda alta?

PASO 5: Contexto macro
- ¿DXY subiendo?
- ¿Gold/Silver > 80?

PASO 6: Conclusión
- Score final con {confidence} de confianza""",

    "CONTRARIAN": """Busca señales de reversión paso a paso:

PASO 1: Extremos de RSI
- ¿RSI < 25 (sobrevendido)?
- ¿RSI > 80 (sobrecompra)?

PASO 2: Divergencias
- ¿Divergencia alcista (precio baja, RSI sube)?
- ¿Divergencia bajista (precio sube, RSI baja)?

PASO 3: Bandas de Bollinger
- ¿Precio fuera de bandas?

PASO 4: Volumen extremo
- ¿Volumen > 3x normal?
- ¿Capitulación o euforia?

PASO 5: Smart Money
- ¿SMI positivo o negativo?

PASO 6: Conclusión
- Score final con {1, 1}""",
}

# ============================================================
# 4. Few-Shot Examples
# ============================================================

FEW_SHOT_EXAMPLES = {
    "BULL": [
        {
            "input": {"close": 150.0, "rsi14": 58.0, "ema20": 148.0, "ema50": 145.0,
                      "ema200": 140.0, "adx14": 28.0, "macd": 1.2, "volume_ratio": 1.3},
            "output": {"score": 0.65, "confidence": 0.8,
                       "reasoning": "Tendencia alcista clara con EMA20>EMA50>EMA200, ADX>25 confirma fuerza, RSI en zona saludable, volumen confirma.",
                       "signals": ["Tendencia alcista confirmada", "ADX fuerte", "Volumen positivo"]}
        },
        {
            "input": {"close": 100.0, "rsi14": 45.0, "ema20": 101.0, "ema50": 102.0,
                      "ema200": 105.0, "adx14": 15.0, "volume_ratio": 0.8},
            "output": {"score": -0.2, "confidence": 0.6,
                       "reasoning": "Tendencia bajista con ADX débil, sin momentum alcista.",
                       "signals": ["Tendencia bajista", "ADX débil"]}
        },
    ],
    "BEAR": [
        {
            "input": {"close": 150.0, "rsi14": 78.0, "ema20": 148.0, "ema50": 145.0,
                      "ema200": 140.0, "adx14": 30.0, "volume_ratio": 1.5},
            "output": {"score": -0.4, "confidence": 0.7,
                       "reasoning": "RSI sobrecompra extrema con volumen alto = posible distribución. Precio sobre banda superior.",
                       "signals": ["RSI sobrecompra", "Volumen alto en máximos"]}
        },
    ],
    "CONTRARIAN": [
        {
            "input": {"close": 100.0, "rsi14": 22.0, "bb_lower": 98.0, "bb_upper": 110.0,
                      "volume_ratio": 3.2, "smi_proxy": 0.15},
            "output": {"score": 0.5, "confidence": 0.8,
                       "reasoning": "RSI sobrevendido extremo con volumen de capitulación y Smart Money comprando = posible fondo.",
                       "signals": ["RSI sobrevendido", "Capitulación", "Smart Money comprando"]}
        },
    ],
}

# ============================================================
# 5. Prompt Templates — Nivel Dios
# ============================================================

GOD_LEVEL_PROMPTS = {
    "BULL": """# 🐂 BULL AGENT — NIVEL DIOS (DeepSeek V4 Flash)

## Identidad
Eres el BULL, un analista cuantitativo de élite con 30 años de experiencia en mercados financieros.
Tu misión: encontrar la evidencia más sólida de que el precio SUBIRÁ.

## Principios de Análisis
1. **Evidencia > Opinión** — Solo cuenta lo que los datos muestran
2. **Confirmación múltiple** — Una señal no es suficiente, busca 3+ confirmaciones
3. **Riesgo primero** — Si el riesgo es alto, reduce el score aunque veas oportunidades
4. **Contexto importa** — Un rally en mercado bajista no es lo mismo que en mercado alcista
5. **Sé honesto** — Si no hay evidencia alcista, dilo con score bajo

## Proceso de Análisis
1. Analiza la tendencia (EMAs, ADX, Ichimoku)
2. Analiza el momentum (RSI, MACD, Momentum 12-1)
3. Analiza el volumen (OBV, CMF, volume ratio)
4. Analiza fundamentales (EPS growth, margins, ROE)
5. Analiza el contexto macro (SPY, DXY, Gold)
6. Sintetiza todo en un score final

## Formato de Respuesta (JSON ESTRICTO)
{{"score": -1.0 a 1.0, "confidence": 0.0 a 1.0, "reasoning": "mínimo 20 caracteres", "signals": ["señal 1", "señal 2"]}}

## Reglas de Validación
- Score DEBE estar entre -1 y 1
- Confidence DEBE estar entre 0 y 1
- Reasoning DEBE tener mínimo 20 caracteres
- NO inventes números que no estén en los datos
- NO respondas fuera del formato JSON""",

    "BEAR": """# 🐻 BEAR ANALYST — NIVEL DIOS (MiniMax M3)

## Identidad
Eres el BEAR, un analista de riesgo de élite especializado en identificar debilidades.
Tu objetivo: encontrar la evidencia más sólida de que el precio BAJARÁ.

## Principios
1. La protección del capital es PRIMERO
2. Busca la debilidad en cada fortaleza aparente
3. La distribución institucional es la señal más poderosa
4. El sobreprecio es el mayor riesgo
5. Sé honesto — si no hay evidencia bajista, dilo

## Proceso
1. Tendencia (¿está el precio bajo las EMAs?)
2. Sobrecompra (RSI, Bollinger, estocástico)
3. Distribución (CMF, volumen, divergencias)
4. Fundamentales débiles (deuda, P/E alto)
5. Macro (DXY, Gold/Silver, VIX)
6. Conclusión con score

## Formato JSON ESTRICTO
{{"score": -1.0 a 1.0, "confidence": 0.0 a 1.0, "reasoning": "...", "signals": [...]}}""",

    "CONTRARIAN": """🔄 CONTRARIAN ANALYST — NIVEL DIOS (GLM 5.2)

## Identidad
Eres el CONTRARIAN, un analista de reversión y manipulación institucional.
Tu objetivo: detectar cuándo el mercado está equivocado.

## Principios
1. El mercado es un mecanismo de transferencia de riqueza
2. La manipulación institucional es real y detectable
3. Los extremos son oportunidades
4. El volumen extremo revela intención
5. La divergencia es la señal más poderosa

## Proceso
1. RSI extremo (sobrecompra/sobreventa)
2. Divergencias (RSI/precio, volumen/precio)
3. Bandas de Bollinger (reversión a media)
4. Volumen extremo (capitulación/euforia)
5. Smart Money (presión al cierre)
6. VIX extremo (fondo de mercado)

## Formato JSON ESTRICTO
{{"score": -1.0 a 1.0, "confidence": 0.0 a 1.0, "reasoning": "...", "signals": [...]}}""",

    "JUDGE": """⚖️ SUPREME JUDGE — NIVEL DIOS (GLM 5.2)

## Identidad
Eres el JUEZ SUPREMO del sistema Fortress Core. Tu veredicto es VINCULANTE.

## Poderes
1. Puedes sobrepasar a cualquier agente
2. Puedes vetar decisiones del CONTROLADOR
3. Tu razonamiento debe ser impecable
4. La justicia es tu única lealtad

## Proceso de Arbitraje
1. Escucha los argumentos de BULL, BEAR y CONTRARIAN
2. Pondera la evidencia de cada uno
3. Considera el contexto macro y de régimen
4. Evalúa el riesgo de cada opción
5. Emite veredicto final

## Formato JSON ESTRICTO
{{"verdict": "COMPRAR/VENDER/MANTENER", "score": -1.0 a 1.0, "reasoning": "...",
  "overruled_agents": [...], "risk_assessment": "BAJO/MEDIO/ALTO",
  "confidence": 0.0 a 1.0, "conditions": [...]}}""",

    "PROFESSOR": """🎓 PROFESSOR — NIVEL DIOS (MiniMax M3)

## Identidad
Eres el PROFESSOR, el agente más sabio del sistema. Enseñas a los demás agentes.

## Conocimiento
Tienes acceso a:
- 28 papers académicos de trading cuantitativo
- Memoria de todas las predicciones pasadas
- Lecciones aprendidas de errores
- Patrones de mercado históricos

## Tu tarea
1. Analiza el rendimiento histórico de cada agente
2. Identifica patrones de error
3. Genera lecciones accionables
4. Ajusta pesos basados en evidencia
5. Alerta sobre condiciones de mercado cambiantes

## Formato JSON ESTRICTO
{{"lessons": [{{"agent": "...", "lesson": "...", "action": "..."}}],
  "weight_adjustments": {{...}}, "alerts": [...], "recommendations": [...],
  "confidence": 0.0 a 1.0}}""",
}

# ============================================================
# 6. PromptEngine — Integración
# ============================================================

class PromptEngine:
    """
    Motor de prompts nivel dios que integra:
    - Contexto RAG + memoria
    - Chain-of-thought
    - Few-shot examples
    - Hardiness checks
    - Self-consistency
    """

    def __init__(self, memory_file: str = "data/prompt_memory.json"):
        self.memory = MemorySystem(memory_file)
        self.hardiness = HardinessChecker()
        self.god_prompts = GOD_LEVEL_PROMPTS
        self.cot_templates = COT_TEMPLATES
        self.few_shot = FEW_SHOT_EXAMPLES

    def build_system_prompt(self, agent: str, include_cot: bool = True,
                            include_few_shot: bool = True) -> str:
        """Construye el system prompt nivel dios para un agente."""
        base = self.god_prompts.get(agent, self.god_prompts["BULL"])

        parts = [base]

        if include_cot and agent in self.cot_templates:
            parts.append("\n## Proceso de Razonamiento\n")
            parts.append(self.cot_templates[agent])

        if include_few_shot and agent in self.few_shot:
            parts.append("\n## Ejemplos de Referencia\n")
            for i, example in enumerate(self.few_shot[agent][:2]):
                parts.append(f"### Ejemplo {i+1}:")
                parts.append(f"Input: {json.dumps(example['input'])}")
                parts.append(f"Output: {json.dumps(example['output'])}")
                parts.append("")

        parts.append("\n## REGLAS CRÍTICAS")
        parts.append("1. Responde SOLO con JSON válido")
        parts.append("2. No inventes datos que no estén en el input")
        parts.append("3. Sé honesto sobre la incertidumbre")
        parts.append("4. La calidad del razonamiento importa más que la dirección")

        return "\n".join(parts)

    def build_user_message(self, agent: str, data: Dict, deterministic_score: float = 0.0,
                           include_memory: bool = True) -> str:
        """Construye el user message con contexto completo."""
        parts = []

        # Datos del análisis
        parts.append("## DATOS DEL ANÁLISIS")
        parts.append(json.dumps(data, indent=2, default=str))

        # Score determinista
        parts.append(f"\n## SCORE DETERMINISTA: {deterministic_score:+.3f}")
        parts.append("Este es el score calculado por el sistema. Confirma o corrige con tu análisis.")

        # Memoria relevante
        if include_memory:
            query = f"{agent} {data.get('symbol', '')} {data.get('rsi14', '')}"
            memory_context = self.memory.get_context(query)
            if memory_context:
                parts.append(f"\n## {memory_context}")

        # Instrucciones finales
        parts.append("\n## RESPUESTA")
        parts.append("Analiza los datos y responde con JSON en el formato especificado.")

        return "\n".join(parts)

    def process_llm_response(self, response: str, agent: str,
                             deterministic_score: float = 0.0,
                             known_values: Optional[Dict] = None) -> Tuple[Optional[Dict], List[str]]:
        """
        Procesa y valida la respuesta del LLM con hardiness checks.

        Returns:
            (data_validado, lista_de_errores)
        """
        errors = []

        # 1. Validar JSON
        data, json_errors = self.hardiness.validate_json_response(response)
        if not data:
            return None, json_errors
        errors.extend(json_errors)

        # 2. Validar contra determinista
        if "score" in data:
            ok, msg = self.hardiness.validate_against_deterministic(
                float(data["score"]), deterministic_score
            )
            if not ok:
                errors.append(msg)

        # 3. Validar consistencia confianza-score
        if "score" in data and "confidence" in data:
            ok, msg = self.hardiness.validate_confidence_consistency(
                float(data["score"]), float(data["confidence"])
            )
            if not ok:
                errors.append(msg)

        # 4. Detectar alucinaciones
        if known_values:
            hallucinations = self.hardiness.detect_hallucination(
                response, known_values
            )
            errors.extend(hallucinations)

        # 5. Registrar en memoria
        if data and not errors:
            self.memory.add(
                content=f"{agent}: score={data.get('score', 0):+.3f}, conf={data.get('confidence', 0):.2f}",
                category="prediction",
                importance=0.6,
                tags=[agent, "llm"],
                source="llm",
            )

        return data, errors

    def self_consistency(self, responses: List[str], agent: str,
                         deterministic_score: float = 0.0) -> Tuple[Optional[Dict], float]:
        """
        Self-consistency: genera múltiples respuestas y vota por la más consistente.

        Returns:
            (respuesta_consistente, nivel_de_consistencia)
        """
        valid_responses = []
        for resp in responses:
            data, errors = self.process_llm_response(resp, agent, deterministic_score)
            if data and not errors:
                valid_responses.append(data)

        if not valid_responses:
            return None, 0.0

        # Votación por score
        scores = [float(d.get("score", 0)) for d in valid_responses]
        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores)) if len(scores) > 1 else 0.0

        # Consistencia: 1 - std (0 = perfecta, 1 = máxima dispersión)
        consistency = max(0.0, 1.0 - std_score)

        # Elegir la respuesta más cercana a la media
        best = min(valid_responses, key=lambda d: abs(float(d.get("score", 0)) - mean))

        return best, consistency

    def get_status(self) -> Dict:
        """Estado del prompt engine."""
        return {
            "memory": self.memory.get_stats(),
            "agents": list(self.god_prompts.keys()),
            "cot_templates": list(self.cot_templates.keys()),
            "few_shot_examples": {k: len(v) for k, v in self.few_shot.items()},
            "hardiness_checks": list(self.hardiness.REQUIRED_FIELDS.keys()),
        }