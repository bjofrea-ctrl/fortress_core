"""
Agentes Evaluadores TRIAD para Fortress Core — Fase 2

Sistema de triple validación de señales:
- Agente BULL: Busca evidencia alcista
- Agente BEAR: Busca evidencia bajista
- Agente CONTRARIAN: Busca señales de reversión y manipulación

Cada agente evalúa independientemente y produce un score en [-1, +1].
El consenso TRIAD combina los tres scores con pesos adaptativos.

Cada agente puede usar un LLM específico de NVIDIA NIM:
- BULL → DeepSeek V4 Flash
- BEAR → MiniMax M3
- CONTRARIAN → GLM 5.2

Referencias:
- Kahneman & Tversky (1979): Prospect Theory — sesgos de confirmación
- Tetlock (2005): Expert political judgment — diversidad de perspectivas
- Surowiecki (2004): Wisdom of crowds — agregación de juicios independientes
"""
import pandas as pd
import numpy as np
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from app.utils.logging import logger
from app.core.prompt_engine import HardinessChecker


@dataclass
class AgentVerdict:
    agent: str  # "BULL", "BEAR", "CONTRARIAN"
    score: float  # -1 a +1
    confidence: float  # 0 a 1
    signals: List[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class TriadConsensus:
    bull_score: float = 0.0
    bear_score: float = 0.0
    contrarian_score: float = 0.0
    consensus_score: float = 0.0
    agreement_level: str = "DIVERGENTE"  # CONVERGENTE, PARCIAL, DIVERGENTE
    verdicts: List[AgentVerdict] = field(default_factory=list)
    final_recommendation: str = "MANTENER"


class BullAgent:
    """Agente alcista: busca evidencia de que el precio subirá."""

    def evaluate(self, df: pd.DataFrame, fundamentals: Optional[Dict] = None,
                 macro_data: Optional[Dict] = None) -> AgentVerdict:
        signals: List[str] = []
        score = 0.0
        confidence = 0.0
        latest = df.iloc[-1]

        # 1. Tendencia alcista (EMA 20 > EMA 50 > EMA 200)
        if "ema20" in latest and "ema50" in latest and "ema200" in latest:
            if latest["ema20"] > latest["ema50"] > latest["ema200"]:
                score += 0.3
                confidence += 0.15
                signals.append("Tendencia alcista: EMA20 > EMA50 > EMA200")
            elif latest["ema20"] > latest["ema50"]:
                score += 0.1
                confidence += 0.05
                signals.append("Tendencia parcialmente alcista")

        # 2. Momentum positivo
        if "momentum_12_1" in latest and pd.notna(latest["momentum_12_1"]):
            mom = float(latest["momentum_12_1"])
            if mom > 20:
                score += 0.2
                confidence += 0.10
                signals.append(f"Momentum 12m fuerte: +{mom:.1f}%")
            elif mom > 0:
                score += 0.1
                confidence += 0.05
                signals.append(f"Momentum 12m positivo: +{mom:.1f}%")

        # 3. RSI en zona saludable (no sobrecompra)
        if "rsi14" in latest and pd.notna(latest["rsi14"]):
            rsi = float(latest["rsi14"])
            if 50 <= rsi <= 65:
                score += 0.15
                confidence += 0.08
                signals.append(f"RSI en zona alcista saludable: {rsi:.1f}")
            elif 40 <= rsi < 50:
                score += 0.05
                confidence += 0.03
                signals.append(f"RSI recuperándose: {rsi:.1f}")

        # 4. MACD alcista
        if "macd" in latest and "macd_signal" in latest:
            if pd.notna(latest["macd"]) and pd.notna(latest["macd_signal"]):
                if latest["macd"] > latest["macd_signal"]:
                    score += 0.15
                    confidence += 0.08
                    signals.append("MACD sobre línea de señal (alcista)")

        # 5. Volumen confirmando subida
        if "volume_ratio" in latest and pd.notna(latest["volume_ratio"]):
            vr = float(latest["volume_ratio"])
            if vr > 1.2 and latest["close"] > latest.get("ema20", latest["close"]):
                score += 0.1
                confidence += 0.05
                signals.append(f"Volumen confirmando: ratio {vr:.2f}")

        # 6. CMF positivo (acumulación)
        if "cmf20" in latest and pd.notna(latest["cmf20"]):
            cmf = float(latest["cmf20"])
            if cmf > 0.1:
                score += 0.1
                confidence += 0.05
                signals.append(f"CMF positivo: {cmf:.3f} (acumulación)")

        # 7. Fundamentales alcistas
        if fundamentals:
            if fundamentals.get("eps_growth") and float(fundamentals["eps_growth"]) > 10:
                score += 0.1
                confidence += 0.05
                signals.append(f"EPS growth fuerte: +{fundamentals['eps_growth']}%")
            if fundamentals.get("gross_margin") and float(fundamentals["gross_margin"]) > 40:
                score += 0.05
                confidence += 0.03
                signals.append(f"Margen bruto alto: {fundamentals['gross_margin']}%")

        # 8. Macro alcista
        if macro_data:
            spy = macro_data.get("SPY")
            if spy is not None and len(spy) > 50:
                spy_ret = float(spy["close"].pct_change(50).iloc[-1] * 100)
                if spy_ret > 5:
                    score += 0.1
                    confidence += 0.05
                    signals.append(f"Mercado general alcista: S&P +{spy_ret:.1f}% en 50d")

        # Normalizar score a [-1, +1]
        score = float(np.clip(score, -1, 1))
        confidence = float(np.clip(confidence, 0, 1))

        reasoning = "Evidencia alcista encontrada" if score > 0.2 else (
            "Evidencia alcista débil" if score > 0 else "Sin evidencia alcista significativa")

        return AgentVerdict(
            agent="BULL",
            score=score,
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
        )


class BearAgent:
    """Agente bajista: busca evidencia de que el precio bajará."""

    def evaluate(self, df: pd.DataFrame, fundamentals: Optional[Dict] = None,
                 macro_data: Optional[Dict] = None) -> AgentVerdict:
        signals: List[str] = []
        score = 0.0
        confidence = 0.0
        latest = df.iloc[-1]

        # 1. Tendencia bajista
        if "ema20" in latest and "ema50" in latest and "ema200" in latest:
            if latest["ema20"] < latest["ema50"] < latest["ema200"]:
                score += 0.3
                confidence += 0.15
                signals.append("Tendencia bajista: EMA20 < EMA50 < EMA200")
            elif latest["ema20"] < latest["ema50"]:
                score += 0.1
                confidence += 0.05
                signals.append("Tendencia parcialmente bajista")

        # 2. Momentum negativo
        if "momentum_12_1" in latest and pd.notna(latest["momentum_12_1"]):
            mom = float(latest["momentum_12_1"])
            if mom < -20:
                score += 0.2
                confidence += 0.10
                signals.append(f"Momentum 12m negativo: {mom:.1f}%")
            elif mom < 0:
                score += 0.1
                confidence += 0.05
                signals.append(f"Momentum 12m negativo: {mom:.1f}%")

        # 3. RSI sobrecompra (probable corrección)
        if "rsi14" in latest and pd.notna(latest["rsi14"]):
            rsi = float(latest["rsi14"])
            if rsi > 75:
                score += 0.2
                confidence += 0.10
                signals.append(f"RSI sobrecompra extrema: {rsi:.1f}")
            elif rsi > 70:
                score += 0.1
                confidence += 0.05
                signals.append(f"RSI sobrecompra: {rsi:.1f}")

        # 4. MACD bajista
        if "macd" in latest and "macd_signal" in latest:
            if pd.notna(latest["macd"]) and pd.notna(latest["macd_signal"]):
                if latest["macd"] < latest["macd_signal"]:
                    score += 0.15
                    confidence += 0.08
                    signals.append("MACD bajo línea de señal (bajista)")

        # 5. Volumen en caída (distribución)
        if "volume_divergence" in latest:
            vol_div = float(latest["volume_divergence"])
            if vol_div > 0.5:
                score += 0.15
                confidence += 0.08
                signals.append("Precio sube con volumen decreciente (distribución)")

        # 6. CMF negativo (distribución)
        if "cmf20" in latest and pd.notna(latest["cmf20"]):
            cmf = float(latest["cmf20"])
            if cmf < -0.1:
                score += 0.15
                confidence += 0.08
                signals.append(f"CMF negativo: {cmf:.3f} (distribución)")

        # 7. Fundamentales bajistas
        if fundamentals:
            if fundamentals.get("debt_equity") and float(fundamentals["debt_equity"]) > 2:
                score += 0.1
                confidence += 0.05
                signals.append(f"Deuda/Equity alto: {fundamentals['debt_equity']}")
            if fundamentals.get("pe_ratio") and float(fundamentals["pe_ratio"]) > 50:
                score += 0.1
                confidence += 0.05
                signals.append(f"P/E elevado: {fundamentals['pe_ratio']}")

        # 8. Macro bajista
        if macro_data:
            dxy = macro_data.get("DXY")
            gold = macro_data.get("gold")
            if dxy is not None and gold is not None and len(dxy) > 30:
                dxy_ret = float(dxy["close"].pct_change(20).iloc[-1] * 100)
                gold_ret = float(gold["close"].pct_change(20).iloc[-1] * 100)
                if dxy_ret > 1 and gold_ret < -1:
                    score += 0.15
                    confidence += 0.08
                    signals.append("Risk-OFF: DXY sube, Oro baja")

        # Normalizar
        score = float(np.clip(score, -1, 1))
        confidence = float(np.clip(confidence, 0, 1))

        reasoning = "Evidencia bajista encontrada" if score > 0.2 else (
            "Evidencia bajista débil" if score > 0 else "Sin evidencia bajista significativa")

        return AgentVerdict(
            agent="BEAR",
            score=score,
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
        )


class ContrarianAgent:
    """Agente contrarian: busca señales de reversión y manipulación."""

    def evaluate(self, df: pd.DataFrame, fundamentals: Optional[Dict] = None,
                 macro_data: Optional[Dict] = None) -> AgentVerdict:
        signals: List[str] = []
        score = 0.0
        confidence = 0.0
        latest = df.iloc[-1]

        # 1. RSI extremo (reversión)
        if "rsi14" in latest and pd.notna(latest["rsi14"]):
            rsi = float(latest["rsi14"])
            if rsi < 25:
                score += 0.3  # Sobrevendido = oportunidad de compra
                confidence += 0.15
                signals.append(f"RSI sobrevendido extremo: {rsi:.1f} (oportunidad)")
            elif rsi > 80:
                score -= 0.3  # Sobrecompra = riesgo de caída
                confidence += 0.15
                signals.append(f"RSI sobrecompra extrema: {rsi:.1f} (riesgo)")

        # 2. Divergencias (manipulación)
        if "bearish_divergence" in latest and latest["bearish_divergence"]:
            score -= 0.25
            confidence += 0.12
            signals.append("Divergencia bajista RSI/precio (distribución institucional)")

        if "bullish_divergence" in latest and latest["bullish_divergence"]:
            score += 0.25
            confidence += 0.12
            signals.append("Divergencia alcista RSI/precio (acumulación institucional)")

        # 3. Bandas de Bollinger (reversión a media)
        if "bb_upper" in latest and "bb_lower" in latest and "close" in latest:
            close = float(latest["close"])
            bb_upper = float(latest["bb_upper"])
            bb_lower = float(latest["bb_lower"])
            if close > bb_upper:
                score -= 0.15
                confidence += 0.08
                signals.append("Precio sobre banda superior (probable reversión a la baja)")
            elif close < bb_lower:
                score += 0.15
                confidence += 0.08
                signals.append("Precio bajo banda inferior (probable rebote)")

        # 4. Volumen extremo (capitulación o euforia)
        if "volume_ratio" in latest and pd.notna(latest["volume_ratio"]):
            vr = float(latest["volume_ratio"])
            if vr > 3.0:
                # Volumen extremo = evento de reversión
                if "close" in latest and "ema20" in latest:
                    if latest["close"] < latest["ema20"]:
                        score += 0.15
                        confidence += 0.08
                        signals.append(f"Volumen extremo en caída: ratio {vr:.1f} (capitulación)")
                    else:
                        score -= 0.15
                        confidence += 0.08
                        signals.append(f"Volumen extremo en subida: ratio {vr:.1f} (euforia)")

        # 5. Smart Money Index (manipulación)
        if "smi_proxy" in latest and pd.notna(latest["smi_proxy"]):
            smi = float(latest["smi_proxy"])
            if smi > 0.1:
                score += 0.1
                confidence += 0.05
                signals.append("Smart Money comprando al cierre")
            elif smi < -0.1:
                score -= 0.1
                confidence += 0.05
                signals.append("Smart Money vendiendo al cierre")

        # 6. Gold/Silver ratio (sentimiento de mercado)
        if macro_data:
            gold = macro_data.get("gold")
            silver = macro_data.get("silver")
            if gold is not None and silver is not None:
                gs = float(gold["close"].iloc[-1] / silver["close"].iloc[-1])
                if gs > 80:
                    score -= 0.1
                    confidence += 0.05
                    signals.append(f"Gold/Silver = {gs:.1f} > 80 (miedo extremo)")
                elif gs < 65:
                    score += 0.1
                    confidence += 0.05
                    signals.append(f"Gold/Silver = {gs:.1f} < 65 (optimismo)")

        # 7. VIX extremo (fondo de mercado)
        if macro_data:
            vix = macro_data.get("VIX") or macro_data.get("^VIX")
            if vix is not None and len(vix) > 20:
                vix_val = float(vix["close"].iloc[-1])
                if vix_val > 30:
                    score += 0.2
                    confidence += 0.10
                    signals.append(f"VIX = {vix_val:.1f} > 30 (miedo extremo, posible fondo)")

        # Normalizar
        score = float(np.clip(score, -1, 1))
        confidence = float(np.clip(confidence, 0, 1))

        reasoning = "Señales de reversión/manipulación detectadas" if abs(score) > 0.2 else (
            "Sin señales contrarian significativas")

        return AgentVerdict(
            agent="CONTRARIAN",
            score=score,
            confidence=confidence,
            signals=signals,
            reasoning=reasoning,
        )


class TriadEvaluator:
    """
    Sistema TRIAD: tres agentes independientes evalúan la misma señal.
    El consenso combina sus juicios para reducir sesgo de confirmación.
    Cada agente puede usar un LLM específico de NVIDIA NIM:
    - BULL → DeepSeek V4 Flash
    - BEAR → MiniMax M3
    - CONTRARIAN → GLM 5.2
    """

    def __init__(self, nim_client=None):
        self.bull_agent = BullAgent()
        self.bear_agent = BearAgent()
        self.contrarian_agent = ContrarianAgent()
        self.nim_client = nim_client

    def _llm_enhance(self, agent: str, verdict: AgentVerdict, df: pd.DataFrame, symbol: str,
                     fundamentals: Optional[Dict], macro_data: Optional[Dict]) -> AgentVerdict:
        """
        Mejora el veredicto del agente usando su LLM específico de NVIDIA NIM.
        Si el LLM no está disponible, usa el veredicto determinista.
        """
        if not self.nim_client or not self.nim_client.is_available():
            return verdict

        # Resumen macro (antes se recibía macro_data pero nunca se usaba acá)
        macro_summary = None
        if macro_data:
            spy = macro_data.get("SPY")
            if spy is not None and len(spy) > 50:
                macro_summary = {"spy_return_50d_pct": round(float(spy["close"].pct_change(50).iloc[-1] * 100), 2)}

        # Construir mensaje con datos del agente
        latest = df.iloc[-1]
        user_message = json.dumps({
            "symbol": symbol,
            "agent": agent,
            "deterministic_score": verdict.score,
            "signals": verdict.signals[:10],
            "close": float(latest.get("close", 0)),
            "rsi14": float(latest.get("rsi14", 0)) if pd.notna(latest.get("rsi14")) else None,
            "ema20": float(latest.get("ema20", 0)) if pd.notna(latest.get("ema20")) else None,
            "ema50": float(latest.get("ema50", 0)) if pd.notna(latest.get("ema50")) else None,
            "ema200": float(latest.get("ema200", 0)) if pd.notna(latest.get("ema200")) else None,
            "adx14": float(latest.get("adx14", 0)) if pd.notna(latest.get("adx14")) else None,
            "macd": float(latest.get("macd", 0)) if pd.notna(latest.get("macd")) else None,
            "volume_ratio": float(latest.get("volume_ratio", 1)) if pd.notna(latest.get("volume_ratio")) else None,
            "cmf20": float(latest.get("cmf20", 0)) if pd.notna(latest.get("cmf20")) else None,
            "fundamentals": fundamentals,
            "macro": macro_summary,
        })

        # Prompt específico por agente
        agent_prompts = {
            "BULL": (
                "Eres un analista alcista experto con acceso a DeepSeek V4 Flash. "
                "Analiza los datos y confirma o corrige el score determinista. "
                "Responde SOLO con JSON: {\"score\": -1.0 a 1.0, \"confidence\": 0.0 a 1.0, "
                "\"reasoning\": \"...\", \"signals\": [\"...\"]}"
            ),
            "BEAR": (
                "Eres un analista bajista experto con acceso a MiniMax M3. "
                "Analiza los datos y confirma o corrige el score determinista. "
                "Responde SOLO con JSON: {\"score\": -1.0 a 1.0, \"confidence\": 0.0 a 1.0, "
                "\"reasoning\": \"...\", \"signals\": [\"...\"]}"
            ),
            "CONTRARIAN": (
                "Eres un analista contrarian experto con acceso a GLM 5.2. "
                "Busca señales de reversión y manipulación institucional. "
                "Analiza los datos y confirma o corrige el score determinista. "
                "Responde SOLO con JSON: {\"score\": -1.0 a 1.0, \"confidence\": 0.0 a 1.0, "
                "\"reasoning\": \"...\", \"signals\": [\"...\"]}"
            ),
        }

        system_prompt = agent_prompts.get(agent, "Eres un analista experto.")
        llm_result = self.nim_client.generate_for_agent(agent, system_prompt, user_message)

        if not llm_result:
            logger.info("triad_llm_fallback_to_deterministic", extra={"agent": agent})
            return verdict

        field_errors = HardinessChecker.validate_fields(llm_result)
        if field_errors:
            logger.warning("triad_llm_hardiness_failed", extra={"agent": agent, "errors": field_errors})
            return verdict

        # Actualizar veredicto con análisis LLM
        try:
            new_score = float(llm_result.get("score", verdict.score))
            new_confidence = float(llm_result.get("confidence", verdict.confidence))
            new_reasoning = llm_result.get("reasoning", verdict.reasoning)
            new_signals = llm_result.get("signals", verdict.signals)

            is_sane, reason = HardinessChecker.validate_against_deterministic(new_score, verdict.score)
            if not is_sane:
                logger.warning("triad_llm_deviation_rejected", extra={"agent": agent, "reason": reason})
                return verdict

            return AgentVerdict(
                agent=agent,
                score=float(np.clip(new_score, -1, 1)),
                confidence=float(np.clip(new_confidence, 0, 1)),
                signals=list(new_signals) if isinstance(new_signals, list) else verdict.signals,
                reasoning=f"{verdict.reasoning} | LLM: {new_reasoning}",
            )
        except Exception:
            return verdict

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        fundamentals: Optional[Dict] = None,
        macro_data: Optional[Dict] = None,
    ) -> TriadConsensus:
        """Evalúa una señal con los tres agentes y produce consenso."""
        bull = self.bull_agent.evaluate(df, fundamentals, macro_data)
        bear = self.bear_agent.evaluate(df, fundamentals, macro_data)
        contrarian = self.contrarian_agent.evaluate(df, fundamentals, macro_data)

        # Mejorar con LLMs de NVIDIA NIM si están disponibles
        bull = self._llm_enhance("BULL", bull, df, symbol, fundamentals, macro_data)
        bear = self._llm_enhance("BEAR", bear, df, symbol, fundamentals, macro_data)
        contrarian = self._llm_enhance("CONTRARIAN", contrarian, df, symbol, fundamentals, macro_data)

        # Consenso: bull - bear + contrarian (contrarian puede sumar o restar)
        consensus = bull.score - bear.score + contrarian.score * 0.5

        # Nivel de acuerdo entre agentes
        if bull.score > 0.2 and bear.score < -0.2:
            agreement = "CONVERGENTE_ALCISTA"
        elif bull.score < -0.2 and bear.score > 0.2:
            agreement = "CONVERGENTE_BAJISTA"
        elif abs(bull.score - bear.score) < 0.15:
            agreement = "DIVERGENTE"
        else:
            agreement = "PARCIAL"

        # Recomendación final
        if consensus > 0.3:
            recommendation = "COMPRAR"
        elif consensus > 0.1:
            recommendation = "COMPRAR_LEVE"
        elif consensus < -0.3:
            recommendation = "VENDER"
        elif consensus < -0.1:
            recommendation = "VENDER_LEVE"
        else:
            recommendation = "MANTENER"

        return TriadConsensus(
            bull_score=float(bull.score),
            bear_score=float(bear.score),
            contrarian_score=float(contrarian.score),
            consensus_score=float(np.clip(consensus, -1, 1)),
            agreement_level=agreement,
            verdicts=[bull, bear, contrarian],
            final_recommendation=recommendation,
        )

    def format_consensus(self, consensus: TriadConsensus) -> str:
        """Formatea el consenso TRIAD para display."""
        # Obtener confianzas de los verdicts
        confidences = {v.agent: v.confidence for v in consensus.verdicts}
        lines = [
            f"=== TRIAD CONSENSUS: {consensus.final_recommendation} ===",
            f"Acuerdo: {consensus.agreement_level}",
            f"Score consenso: {consensus.consensus_score:+.3f}",
            "",
            f"🐂 BULL: {consensus.bull_score:+.3f} (conf: {confidences.get('BULL', 0):.0%})",
            f"🐻 BEAR: {consensus.bear_score:+.3f} (conf: {confidences.get('BEAR', 0):.0%})",
            f"🔄 CONTRARIAN: {consensus.contrarian_score:+.3f} (conf: {confidences.get('CONTRARIAN', 0):.0%})",
        ]
        for v in consensus.verdicts:
            if v.signals:
                lines.append(f"\n  {v.agent} señales:")
                for s in v.signals[:5]:
                    lines.append(f"    • {s}")
        return "\n".join(lines)