"""
Repositorio de Conocimiento Fortress Core — RAG + OKF

Sistema de memoria de enseñanza con:
- RAG (Retrieval-Augmented Generation): recupera conocimiento relevante por contexto
- OKF (Organized Knowledge Framework): estructura jerárquica de conocimiento

Dominios de conocimiento:
1. MACROECONOMÍA: Fed, inflación, tasas, ciclos, correlaciones entre activos
2. MICROECONOMÍA: fundamentales de empresas, ratios financieros
3. TRADING: estrategias, gestión de riesgo, ejecución
4. INDICADORES: análisis técnico respaldado por bibliografía académica

Referencias:
- Lewis et al. (2020): Retrieval-Augmented Generation for Knowledge-Intensive NLP
- Robertson & Zaragoza (2009): BM25 — probabilistic retrieval
- Sutton & Barto (2018): aprendizaje por refuerzo
"""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

from app.utils.logging import logger
from app.utils.persistence import atomic_write_json

# ============================================================
# OKF — Estructura de Conocimiento Organizado
# ============================================================

OKF_STRUCTURE = {
    "macroeconomia": {
        "description": "Conocimiento macroeconómico y ciclos de mercado",
        "topics": [
            "fed_política_monetaria",
            "inflación_y_tasas",
            "ciclos_económicos",
            "correlaciones_activos",
            "índices_macro",
            "divisas_dxy",
            "commodities",
        ],
        "papers": [
            "Wolfers & Zitzewitz (2004): Prediction Markets",
            "Whaley (2000): VIX Investor Fear Gauge",
            "Fama & French (1988): Dividend Yields",
        ],
    },
    "microeconomia": {
        "description": "Fundamentales de empresas y ratios financieros",
        "topics": [
            "ratios_valoración",
            "rentabilidad",
            "liquidez",
            "estructura_capital",
            "crecimiento",
            "calidad_ganancias",
        ],
        "papers": [
            "Basu (1977): P/E effect",
            "Fama & French (1992): Value factors",
            "Novy-Marx (2013): Gross profitability",
            "Sloan (1996): Accruals",
            "Altman (1968): Z-Score",
        ],
    },
    "trading": {
        "description": "Estrategias de trading, riesgo y ejecución",
        "topics": [
            "gestión_riesgo",
            "position_sizing",
            "momentum",
            "mean_reversion",
            "breakout",
            "manipulación_institucional",
        ],
        "papers": [
            "Jegadeesh & Titman (1993): Momentum",
            "Brock et al. (1992): Moving averages",
            "Goldstein & Guembel (2008): Manipulation",
            "Kyle (1985): Insider trading",
        ],
    },
    "indicadores": {
        "description": "Indicadores técnicos con respaldo académico",
        "topics": [
            "momentum_indicators",
            "reversion_indicators",
            "volatility_indicators",
            "volume_indicators",
            "trend_indicators",
            "fundamental_indicators",
        ],
        "papers": [
            "Wilder (1978): RSI, ADX, ATR, SAR",
            "Chong & Ng (2008): RSI and MACD",
            "Lento et al. (2007): Bollinger Bands",
            "Amihud (2002): Illiquidity",
        ],
    },
}


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class KnowledgeEntry:
    id: str
    domain: str          # macroeconomia, microeconomia, trading, indicadores
    topic: str
    title: str
    content: str
    source: str          # paper, libro, observación empírica
    year: int = 0
    tags: List[str] = field(default_factory=list)
    embeddings: Optional[List[float]] = None
    created_at: str = ""


# ============================================================
# Repositorio de Conocimiento
# ============================================================

class KnowledgeRepository:
    """
    Repositorio de conocimiento con búsqueda RAG.
    Almacena conocimiento académico, empírico y de aprendizaje.
    """

    def __init__(self, repo_file: str = "data/knowledge_repo.json"):
        self.repo_file = repo_file
        self.entries: List[KnowledgeEntry] = []
        self._load()
        self._seed_default_knowledge()

    def _load(self):
        """Carga conocimiento persistente."""
        if os.path.exists(self.repo_file):
            try:
                with open(self.repo_file, "r") as f:
                    data = json.load(f)
                    self.entries = [KnowledgeEntry(**e) for e in data.get("entries", [])]
            except Exception as e:
                logger.error("knowledge_repo_load_failed", extra={"file": self.repo_file, "error": str(e)})

    def _save(self):
        """Guarda conocimiento persistente."""
        data = {"entries": [e.__dict__ for e in self.entries]}
        atomic_write_json(self.repo_file, data)

    def add_entry(self, domain: str, topic: str, title: str, content: str,
                  source: str, year: int = 0, tags: List[str] = None) -> KnowledgeEntry:
        """Agrega una entrada de conocimiento."""
        entry = KnowledgeEntry(
            id=f"{domain}_{topic}_{len(self.entries)}_{datetime.now().timestamp():.0f}",
            domain=domain,
            topic=topic,
            title=title,
            content=content,
            source=source,
            year=year,
            tags=tags or [],
            created_at=str(datetime.now()),
        )
        self.entries.append(entry)
        self._save()
        return entry

    def _tokenize(self, text: str) -> Set[str]:
        """Tokeniza texto para búsqueda."""
        return set(re.findall(r'\w+', text.lower()))

    def search(self, query: str, domain: Optional[str] = None,
               top_k: int = 5) -> List[KnowledgeEntry]:
        """
        Búsqueda RAG: recupera entradas relevantes por similitud (Jaccard + keyword).
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for entry in self.entries:
            if domain and entry.domain != domain:
                continue
            entry_tokens = self._tokenize(entry.title + " " + entry.content + " " + " ".join(entry.tags))
            # Jaccard similarity
            intersection = len(query_tokens & entry_tokens)
            union = len(query_tokens | entry_tokens)
            jaccard = intersection / union if union > 0 else 0
            scored.append((jaccard, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for s, e in scored[:top_k] if s > 0]

    def get_context_for_prompt(self, query: str, domain: Optional[str] = None,
                               top_k: int = 3) -> str:
        """Genera contexto RAG para prompts LLM."""
        results = self.search(query, domain, top_k)
        if not results:
            return ""
        lines = ["[CONTEXTO DE CONOCIMIENTO RECUPERADO]"]
        for e in results:
            lines.append(f"--- {e.title} ({e.source} {e.year if e.year else ''}) ---")
            lines.append(e.content[:500])
            lines.append("")
        return "\n".join(lines)

    def _seed_default_knowledge(self):
        """Siembra conocimiento académico inicial."""
        if self.entries:
            return

        seed_data = [
            # MACROECONOMÍA
            ("macroeconomia", "fed_política_monetaria",
             "Política monetaria de la Fed y mercados",
             "La Fed controla la tasa de fondos federales. Recortes de tasas tienden a ser alcistas para acciones (liquidez), subidas tienden a ser bajistas. El mercado anticipa movimientos de la Fed a través de futuros y markets de predicción.",
             "Bordo & Wheelock (2012), Wolfers & Zitzewitz (2004)", 2012,
             ["fed", "tasas", "liquidez", "política monetaria"]),

            ("macroeconomia", "inflación_y_tasas",
             "Inflación y su efecto en acciones",
             "Inflación alta (>4%) erosiona múltiplos P/E y favorece commodities (oro, plata, petróleo) y TIPS. Inflación moderada en expansión puede ser alcista. Estanflación (inflación alta + crecimiento bajo) es muy negativa para acciones.",
             "Fama & French (1988), Novy-Marx (2013)", 1988,
             ["inflación", "tasas", "commodities", "estanflación"]),

            ("macroeconomia", "correlaciones_activos",
             "Correlaciones históricas entre activos",
             "DXY-Oro: -0.35 promedio histórico. DXY-S&P500: -0.25. Oro-Plata: +0.80. Cobre-S&P500: +0.45. DXY bajando + Oro subiendo = Risk-ON (alcista acciones). DXY subiendo + Oro bajando = Risk-OFF (bajista). Gold/Silver > 80 = miedo, < 65 = optimismo.",
             "Análisis empírico 1990-2024", 2024,
             ["dxy", "oro", "plata", "correlaciones", "risk-on", "risk-off"]),

            ("macroeconomia", "commodities",
             "Cobre como leading indicator",
             "El cobre es considerado 'Dr. Copper' por su capacidad predictiva. Cobre sobre MA200 = expansión económica (alcista para acciones). Cobre bajo MA200 = contracción (bajista). Petróleo subiendo >10% en 20d = presión inflacionaria (bajista).",
             "Análisis empírico + literatura de commodities", 2024,
             ["cobre", "petróleo", "leading indicators", "expansión"]),

            # MICROECONOMÍA
            ("microeconomia", "ratios_valoración",
             "Ratios de valoración y retornos",
             "P/E bajo predice mayores retornos (Basu 1977). Book-to-market alto predice retornos (Fama-French 1992). FCF Yield es el mejor valor predictivo de valoración (Lakonishok et al. 1994). EV/EBITDA ajusta por estructura de capital (Loughran & Wellman 2011).",
             "Basu (1977), Fama & French (1992), Lakonishok et al. (1994), Loughran & Wellman (2011)", 1977,
             ["pe", "pb", "fcf", "ev/ebitda", "valor"]),

            ("microeconomia", "rentabilidad",
             "Rentabilidad y retornos de acciones",
             "ROE alto predice retornos superiores (Fama-French 2006). Gross Margin es el 'gross profitability premium' (Novy-Marx 2013): empresas con margen bruto alto generan retornos superiores. ROA con cash flow real = calidad de ganancias (Sloan 1996).",
             "Fama & French (2006), Novy-Marx (2013), Sloan (1996)", 2013,
             ["roe", "roa", "gross margin", "rentabilidad"]),

            ("microeconomia", "estructura_capital",
             "Estructura de capital y riesgo",
             "Alto leverage (deuda/equity > 2) aumenta riesgo de quiebra (Altman Z-Score 1968). Empresas con deuda excesiva tienen retornos esperados menores ajustados por riesgo. Current Ratio < 1 = riesgo de liquidez (Graham & Dodd 1934).",
             "Altman (1968), Graham & Dodd (1934)", 1968,
             ["deuda", "leverage", "z-score", "liquidez"]),

            ("microeconomia", "calidad_ganancias",
             "Calidad de ganancias y accruals",
             "Accruals altos (ganancias contables sin cash) predicen retornos negativos (Sloan 1996). SUE (Standardized Unexpected Earnings) genera PEAD: drift post-anuncio de 60+ días (Bernard & Thomas 1989). Sorpresas positivas de EPS continúan generando retornos.",
             "Sloan (1996), Bernard & Thomas (1989)", 1996,
             ["accruals", "sue", "pead", "calidad ganancias"]),

            # TRADING
            ("trading", "gestión_riesgo",
             "Gestión de riesgo esencial",
             "Nunca arriesgar más de 1.5% del equity por trade. Ceiling absoluto de drawdown 12%. Stops por régimen: 5% bull, 7% reflation, 8% stagflation, 3% deflation. Position sizing: riesgo 1.5% / ATR * 2. Posición máxima 10% del equity.",
             "Van Tharp (1987), Wilder (1978)", 1987,
             ["riesgo", "stops", "position sizing", "drawdown"]),

            ("trading", "momentum",
             "Momentum como estrategia",
             "Momentum de 12 meses excluyendo el último mes (12-1) predice retornos ~1% mensual (Jegadeesh & Titman 1993). Momentum en ganancias (EPS revisiones) también predice (Chan et al. 1996). Comprar ganadores y vender perdedores.",
             "Jegadeesh & Titman (1993), Chan et al. (1996)", 1993,
             ["momentum", "12-1", "ganadores", "perdedores"]),

            ("trading", "mean_reversion",
             "Reversión a la media",
             "RSI < 30 = sobrevendido (oportunidad), RSI > 70 = sobrecompra (riesgo). Precio bajo banda inferior de Bollinger = probable rebote. Osciladores estocásticos en extremos generan señales de reversión. Más efectivo en mercados de rango.",
             "Wilder (1978), Lane (1984), Lento et al. (2007)", 1984,
             ["rsi", "bollinger", "estocástico", "reversión"]),

            ("trading", "manipulación_institucional",
             "Manipulación institucional del mercado",
             "El ciclo institucional: ACUMULAR en silencio → MARKUP con noticias → VENDER a retail en máximos → MARKDOWN con miedo → RECOMPRAR barato. Señales: divergencias RSI/precio, volumen alto sin nuevos máximos, CMF negativo, A/D Line cayendo, rallies sin volumen.",
             "Goldstein & Guembel (2008), Kyle (1985), Hendershott et al. (2011)", 2008,
             ["manipulación", "smart money", "distribución", "institucional"]),

            # INDICADORES
            ("indicadores", "momentum_indicators",
             "Indicadores de momentum",
             "MACD (12/26/9): cruce sobre señal = alcista. ADX > 25 = tendencia fuerte. Donchian 20d: breakout = entrada Turtle. Parabolic SAR: precio sobre SAR = tendencia alcista. Ichimoku: precio sobre nube = alcista. Momentum 12-1 es el más robusto.",
             "Appel (1979), Wilder (1978), Chong & Ng (2008)", 1979,
             ["macd", "adx", "donchian", "sar", "ichimoku", "momentum"]),

            ("indicadores", "reversion_indicators",
             "Indicadores de reversión",
             "RSI (14): >75 sobrecompra extrema, <25 sobrevendido extremo. Williams %R: <-80 sobrevendido, >-20 sobrecompra. CCI: >+100 sobrecompra, <-100 sobreventa. MFI combina precio y volumen. Estocástico %K >80 = sobrecompra.",
             "Wilder (1978), Lane (1984), Lambert (1980), Eom et al. (2019)", 1978,
             ["rsi", "williams", "cci", "mfi", "estocástico"]),

            ("indicadores", "volatility_indicators",
             "Indicadores de volatilidad",
             "ATR mide rango promedio verdadero; esencial para position sizing y stops. VIX > 30 = miedo extremo (posible fondo), VIX < 15 = complacencia (riesgo). Volatilidad realizada > 40% = reducir tamaño. ATR% > 5% = alta volatilidad.",
             "Wilder (1978), Whaley (2000), Giot (2005)", 1978,
             ["atr", "vix", "volatilidad", "riesgo"]),

            ("indicadores", "volume_indicators",
             "Indicadores de volumen",
             "OBV acumula volumen por dirección de precio. CMF > 0.2 = acumulación fuerte, <-0.2 = distribución. A/D Line mide flujo de acumulación. Volumen > 2x media + precio sube = tendencia confirmada. Volumen alto sin nuevos máximos = distribución.",
             "Granville (1963), Blume, Easley & O'Hara (1994), Amihud (2002)", 1963,
             ["obv", "cmf", "ad line", "volumen", "liquidez"]),

            ("indicadores", "trend_indicators",
             "Indicadores de tendencia",
             "Cruce SMA 50/200 (Golden Cross) = señal alcista fuerte (Brock et al. 1992). EMA20 > EMA50 > EMA200 = tendencia alcista confirmada. ADX > 25 valida tendencia. Ichimoku Cloud combina tendencia y soporte/resistencia.",
             "Brock, Lakonishok & LeBaron (1992), Katsanos (2008)", 1992,
             ["sma", "ema", "golden cross", "adx", "ichimoku", "tendencia"]),
        ]

        for domain, topic, title, content, source, year, tags in seed_data:
            self.add_entry(domain, topic, title, content, source, year, tags)

    def get_domains(self) -> List[str]:
        """Lista dominios de conocimiento."""
        return list(OKF_STRUCTURE.keys())

    def get_stats(self) -> Dict:
        """Estadísticas del repositorio."""
        domains = {}
        for e in self.entries:
            domains[e.domain] = domains.get(e.domain, 0) + 1
        return {
            "total_entries": len(self.entries),
            "by_domain": domains,
        }

    def get_all_titles(self) -> List[str]:
        """Lista todos los títulos de conocimiento."""
        return [e.title for e in self.entries]


# ============================================================
# RAG Memory System — Memoria de Enseñanza
# ============================================================

class RAGMemorySystem:
    """
    Sistema de memoria RAG para el PROFESSOR.
    - OKF (Organized Knowledge Framework): estructura jerárquica
    - RAG: recupera conocimiento relevante por contexto
    - Memoria de lecciones pasadas para enseñar a los agentes
    """

    def __init__(self, memory_file: str = "data/rag_memory.json"):
        self.memory_file = memory_file
        self.lesson_history: List[Dict] = []
        self.agent_knowledge: Dict[str, List[str]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                    self.lesson_history = data.get("lesson_history", [])
                    self.agent_knowledge = data.get("agent_knowledge", {})
            except Exception as e:
                logger.error("rag_memory_load_failed", extra={"file": self.memory_file, "error": str(e)})

    def _save(self):
        data = {
            "lesson_history": self.lesson_history[-200:],
            "agent_knowledge": self.agent_knowledge,
        }
        atomic_write_json(self.memory_file, data)

    def record_lesson(self, agent: str, lesson: str, context: str, outcome: str):
        """Registra una lección enseña al agente."""
        record = {
            "agent": agent,
            "lesson": lesson,
            "context": context,
            "outcome": outcome,
            "timestamp": str(datetime.now()),
        }
        self.lesson_history.append(record)
        if agent not in self.agent_knowledge:
            self.agent_knowledge[agent] = []
        self.agent_knowledge[agent].append(lesson)
        self.agent_knowledge[agent] = self.agent_knowledge[agent][-50:]
        self._save()

    def retrieve_agent_memory(self, agent: str, query: str, top_k: int = 3) -> str:
        """Recupera memoria relevante para un agente."""
        if not self.agent_knowledge.get(agent):
            return ""

        query_tokens = set(re.findall(r'\w+', query.lower()))
        scored = []
        for lesson in self.agent_knowledge[agent]:
            tokens = set(re.findall(r'\w+', lesson.lower()))
            inter = len(query_tokens & tokens)
            union = len(query_tokens | tokens)
            score = inter / union if union > 0 else 0
            scored.append((score, lesson))

        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [lesson for s, lesson in scored[:top_k] if s > 0]
        if not relevant:
            return ""
        return "[MEMORIA DE ENSEÑANZA PREVIA]\n" + "\n".join(f"- {lesson}" for lesson in relevant)

    def get_memory_context(self, agent: str, query: str) -> str:
        """Contexto de memoria para prompts LLM."""
        memory = self.retrieve_agent_memory(agent, query)
        recent = [h for h in self.lesson_history if h["agent"] == agent][-5:]
        lines = []
        if memory:
            lines.append(memory)
        if recent:
            lines.append("\n[Lecciones recientes]")
            for r in recent:
                lines.append(f"- {r['lesson']} (outcome: {r['outcome']})")
        return "\n".join(lines)

    def get_stats(self) -> Dict:
        return {
            "total_lessons": len(self.lesson_history),
            "agents": list(self.agent_knowledge.keys()),
            "lessons_per_agent": {k: len(v) for k, v in self.agent_knowledge.items()},
        }
