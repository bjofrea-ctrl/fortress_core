"""API routes para el motor predictivo Fortress Core Fase 2."""
import asyncio
import time
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.api.rate_limit import RateLimitDependency
from app.api.routes.opportunities_universe import SYMBOLS
from app.config import settings
from app.core.data_ingestion import download_data
from app.core.edgar_fundamentals import get_fundamentals
from app.core.fundamentals_client import FinnhubClient
from app.core.predictive_engine import PredictiveEngine, format_recommendation
from app.utils.logging import logger

_finnhub_client = FinnhubClient()

router = APIRouter(prefix="/api/predict", tags=["predict"])

# Endpoint LLM sin auth: protege la cuota de NVIDIA NIM (no hay datos sensibles).
llm_rate_limit = RateLimitDependency()

CACHE_DIR = "data/cache"
MAX_SIGNALS = 15  # Mostrar los 15 indicadores más relevantes

# Símbolos macro para correlaciones
MACRO_TICKERS = {
    "DXY": "DX-Y.NYB",
    "gold": "GC=F",
    "silver": "SI=F",
    "TLT": "TLT",
    "SPY": "SPY",
    "oil": "CL=F",
    "copper": "HG=F",
}

# Datos fundamentales point-in-time: panel EDGAR local (filing dates reales)
# con degradación a sample marcado. SAMPLE_FUNDAMENTALS vive en
# app/core/edgar_fundamentals.py (junto al cargador EDGAR).

# prediction_data (señales estilo Polymarket) nunca se conectó a una fuente
# real -- se pasaba un dict hardcodeado (SAMPLE_PREDICTION_DATA) como si fuera
# dato real, entrando al composite_score etiquetado "Polymarket: ..." sin
# ningún marcador de que era de ejemplo (violación de ONBOARDING.md regla #4).
# Eliminado 2026-08-25 (hallazgo H1.1, auditoría externa GLM). engine.analyze()
# recibe prediction_data=None hasta que haya una fuente real conectada.


def get_fundamentals_api(symbol: str) -> Optional[dict]:
    """
    Fundamentales point-in-time: panel EDGAR local (filing dates reales de
    SEC, ratios derivados con precio del día de trading siguiente). Si el
    panel no cubre el símbolo/fecha, degrada al sample hardcodeado
    (SAMPLE_FUNDAMENTALS) — siempre marcado en _data_source para que la API
    y cualquier prompt de LLM sepan si es real o sintético.
    """
    data = get_fundamentals(symbol)
    if data is None:
        logger.info("fundamentals_unavailable", extra={"symbol": symbol})
    return data


def _load_macro_data() -> dict:
    """Carga datos macro desde cache o descarga."""
    macro_data = {}
    for name, ticker in MACRO_TICKERS.items():
        try:
            df = download_data(ticker, "2020-01-01")
            if len(df) > 30:
                macro_data[name] = df
        except Exception:
            continue
    return macro_data


# Cache en memoria + offload a threadpool (H2.3, 2026-08-25 — MISMO patrón que
# advisor.py::_get_context, HANDOFF 2026-08-19): analyze_symbol/analyze_universe
# llamaban download_data por request sin cachear — /universe hacía ~57 lecturas
# parquet/red por request y analyze_symbol bloqueaba el event loop con I/O
# síncrono. TTL 5 min: los precios no cambian más rápido que eso para este uso
# de solo-lectura. El lock asyncio evita manada (requests concurrentes
# disparando la misma carga cara a la vez). Trade-off aceptado: /macro-
# correlations en frío también carga el universo (comparten cache; la UI los
# pide juntos y el TTL lo amortiza).
_DATA_CACHE_TTL_SECONDS = 300
_data_lock = asyncio.Lock()
_data_cache: Optional[tuple] = None  # (precios_universo: dict, macro: dict)
_data_cache_time: float = 0.0


def _load_universe_prices_sync() -> dict:
    """Precios del universo canónico; descarta series <200 filas (mismo filtro
    que aplicaba /universe por símbolo)."""
    out = {}
    for s in SYMBOLS:
        try:
            df = download_data(s, "2015-01-01")
        except Exception:
            continue
        if len(df) >= 200:
            out[s] = df
    return out


async def _get_data() -> tuple:
    """(precios_universo, macro) cacheados TTL 5 min, carga en threadpool."""
    global _data_cache, _data_cache_time
    async with _data_lock:
        now = time.monotonic()
        if _data_cache is not None and (now - _data_cache_time) < _DATA_CACHE_TTL_SECONDS:
            return _data_cache
        prices = await run_in_threadpool(_load_universe_prices_sync)
        macro = await run_in_threadpool(_load_macro_data)
        _data_cache = (prices, macro)
        _data_cache_time = time.monotonic()
        return _data_cache


def _load_sentiment_data() -> Optional[dict]:
    """Carga V1 (AAII bull-bear) para el request en vivo.

    - fetch_aaii() lee el parquet con TTL semanal: la descarga del xls ocurre
      como máximo 1 vez/semana, nunca por request; si la descarga falla,
      degrada al cache stale.
    - Alineación anti-lookahead: solo se usa el valor publicado ANTES de hoy
      (AAII publica los jueves tras el cierre -> shift(1)).
    - Cualquier fallo devuelve None: el motor degrada a baseline
      (analyze(sentiment_data=None) es backward-compatible).
    """
    try:
        from app.core.market_sentiment import fetch_aaii
        aaii = fetch_aaii()
        if aaii is None or len(aaii) == 0:
            return None
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
        valid = aaii[aaii.index < cutoff]
        if valid.empty:
            return None
        return {"aaii_bullbear_spread": float(valid.iloc[-1])}
    except Exception:
        logger.warning("sentiment_data_unavailable_degrading_to_baseline")
        return None


def _serialize_result(result, fundamentals_source: str = "unavailable") -> dict:
    """Serializa PredictionResult a dict para JSON.

    AUDITORIA_NIVEL_DIOS_20260902 F0.2 — etiquetado honesto del motor:
    - `motor: "heuristico_no_validado"` declara explícitamente que este
      endpoint NO pasó por el ledger/DSR (a diferencia de signal_engine.py).
    - `probabilidades_calibradas: False` advierte que las prob_up_* son
      scores normalizados a [0,1], NO probabilidades calibradas contra
      frecuencias empíricas. Un consumidor externo NO debe interpretarlas
      como P(real).
    - `confidence` se mantiene como campo string categórico (Baja/Media/
      Alta) — NO es probabilidad.
    - A9: `governance_mode: "descriptive_only"` cuando
      `settings.GOVERNANCE_LLM_ENABLED` está apagado (default durante
      el gate de 60 días). El consumidor sabe que la tríada viene
      del fallback determinista — no de NIM. El motor validado
      (signal_engine.py) no consume esta capa (D1, auditoría).
    """
    governance_mode = "active" if settings.GOVERNANCE_LLM_ENABLED else "descriptive_only"
    return {
        # Identidad del motor (NUEVO, F0.2)
        "motor": result.motor,                          # siempre "heuristico_no_validado" hasta que se valide
        "probabilidades_calibradas": result.probabilidades_calibradas,  # siempre False hasta calibrar
        # A9: estado de la capa multi-agente. "descriptive_only" = la tríada
        # y la gobernanza caen al fallback determinista (no se queman
        # llamadas a NIM durante el gate). "active" = modo completo con LLM.
        "governance_mode": governance_mode,
        # Datos básicos
        "symbol": result.symbol,
        "timestamp": result.timestamp,
        "regime_state": result.regime_state,
        "regime_name": result.regime_name,
        "technical_score": round(result.technical_score, 4),
        "fundamental_score": round(result.fundamental_score, 4),
        "macro_score": round(result.macro_score, 4),
        "sentiment_score": round(result.sentiment_score, 4),
        "volatility_score": round(result.volatility_score, 4),
        "composite_score": round(result.composite_score, 4),
        "decision": result.decision,
        # `confidence` es categórico (Baja/Media/Alta), NO probabilidad
        "confidence": result.confidence,
        # Probabilidades (scores normalizados, NO calibradas)
        "prob_up_short": round(result.prob_up_short, 4),
        "prob_up_medium": round(result.prob_up_medium, 4),
        "prob_up_long": round(result.prob_up_long, 4),
        "manipulation_risk": round(result.manipulation_risk, 4),
        "manipulation_signals": result.manipulation_signals,
        "triad_score": round(result.triad_score, 4),
        "triad_recommendation": result.triad_recommendation,
        "triad_agreement": result.triad_agreement,
        "triad_bull": round(result.triad_consensus.bull_score, 4) if result.triad_consensus else 0.0,
        "triad_bear": round(result.triad_consensus.bear_score, 4) if result.triad_consensus else 0.0,
        "triad_contrarian": round(result.triad_consensus.contrarian_score, 4) if result.triad_consensus else 0.0,
        "fundamentals_source": fundamentals_source,
        "signals": [
            {
                "name": s.name,
                "category": s.category,
                "value": round(float(s.value), 4) if s.value is not None else None,
                "signal": round(float(s.signal), 4),
                "weight": round(float(s.weight), 4),
                "explanation": s.explanation,
            }
            for s in result.signals[:MAX_SIGNALS]
        ],
        "recommendation_text": format_recommendation(result),
    }


@router.get("/analyze/{symbol}", dependencies=[Depends(llm_rate_limit)])
async def analyze_symbol(symbol: str, regime_state: int = Query(0, ge=0, le=3)):
    """Analiza un símbolo con el motor predictivo completo."""
    try:
        # Precios + macro del cache compartido (TTL 5 min, threadpool)
        prices, macro_data = await _get_data()

        # Cargar datos del símbolo (del universo cacheado; si es ajeno al
        # universo canónico, descarga directa también offloaded al threadpool)
        df = prices.get(symbol.upper())
        if df is None:
            df = await run_in_threadpool(download_data, symbol.upper(), "2015-01-01")
        if len(df) < 200:
            raise HTTPException(status_code=404, detail=f"Datos insuficientes para {symbol}")

        # V1 (AAII): degrada a None (baseline) si el fetch falla
        sentiment_data = _load_sentiment_data()

        # Datos fundamentales de muestra
        fundamentals = get_fundamentals_api(symbol)

        # Crear motor
        engine = PredictiveEngine()
        # analyze() puede llamar a NIM (BULL/BEAR/CONTRARIAN) de forma
        # síncrona; correrlo en threadpool evita congelar el event loop.
        result = await run_in_threadpool(
            engine.analyze,
            symbol=symbol.upper(),
            df=df,
            regime_state=regime_state,
            fundamentals=fundamentals,
            macro_data=macro_data,
            prediction_data=None,
            sentiment_data=sentiment_data,
        )

        fundamentals_source = fundamentals.get("_data_source", "unavailable") if fundamentals else "unavailable"
        return _serialize_result(result, fundamentals_source=fundamentals_source)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analizando {symbol}: {str(e)}")


@router.get("/universe")
async def analyze_universe(regime_state: int = Query(0, ge=0, le=3)):
    """Analiza todos los símbolos del universo canónico y los rankea."""
    engine = PredictiveEngine()
    prices, macro_data = await _get_data()
    sentiment_data = _load_sentiment_data()
    results = []

    for symbol in sorted(prices):
        try:
            df = prices[symbol]

            fundamentals = get_fundamentals_api(symbol)
            result = await run_in_threadpool(
                engine.analyze,
                symbol=symbol.upper(),
                df=df,
                regime_state=regime_state,
                fundamentals=fundamentals,
                macro_data=macro_data,
                prediction_data=None,
                sentiment_data=sentiment_data,
            )
            results.append({
                "symbol": result.symbol,
                "decision": result.decision,
                "confidence": result.confidence,
                "composite_score": round(result.composite_score, 4),
                "prob_up_short": round(result.prob_up_short, 4),
                "prob_up_medium": round(result.prob_up_medium, 4),
                "prob_up_long": round(result.prob_up_long, 4),
                "manipulation_risk": round(result.manipulation_risk, 4),
                "manipulation_signals": result.manipulation_signals,
            })
        except Exception:
            continue

    # Sort por score compuesto
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return {"regime_state": regime_state, "symbols": results, "count": len(results)}


@router.get("/macro-correlations")
async def get_macro_correlations():
    """Analiza correlaciones actuales entre activos macro (dólar, oro, plata, etc.)."""
    try:
        _, macro_data = await _get_data()
        engine = PredictiveEngine()
        correlations = engine.analyze_macro_correlations(macro_data)

        # Also include current prices
        prices = {}
        for name, df in macro_data.items():
            if len(df) > 0:
                latest = df.iloc[-1]
                prices[name] = {
                    "price": round(float(latest["close"]), 2),
                    "return_20d_pct": round(float(latest["close"] / df["close"].iloc[-21] - 1) * 100, 2) if len(df) > 21 else 0,
                    "return_90d_pct": round(float(latest["close"] / df["close"].iloc[-91] - 1) * 100, 2) if len(df) > 91 else 0,
                }

        return {
            "prices": prices,
            "correlations": correlations,
            "risk_regime": _assess_risk_regime(macro_data),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en correlaciones: {str(e)}")


def _assess_risk_regime(macro_data: dict) -> dict:
    """Evalúa el régimen de riesgo basado en correlaciones macro."""
    assessment = {
        "regime": "NEUTRAL",
        "score": 0.0,
        "signals": [],
    }

    dxy = macro_data.get("DXY")
    gold = macro_data.get("gold")
    silver = macro_data.get("silver")
    spy = macro_data.get("SPY")
    copper = macro_data.get("copper")

    score = 0.0

    # DXY vs Oro
    if dxy is not None and gold is not None and len(dxy) > 30:
        dxy_ret = float(dxy["close"].pct_change(20).iloc[-1] * 100)
        gold_ret = float(gold["close"].pct_change(20).iloc[-1] * 100)
        if dxy_ret < -1 and gold_ret > 1:
            score += 1.0
            assessment["signals"].append("DXY baja + Oro sube = Risk-ON")
        elif dxy_ret > 1 and gold_ret < -1:
            score -= 1.0
            assessment["signals"].append("DXY sube + Oro baja = Risk-OFF")

    # Gold/Silver ratio
    if gold is not None and silver is not None:
        gs = float(gold["close"].iloc[-1] / silver["close"].iloc[-1])
        if gs > 80:
            score -= 0.5
            assessment["signals"].append(f"Gold/Silver = {gs:.1f} > 80 (miedo)")
        elif gs < 65:
            score += 0.5
            assessment["signals"].append(f"Gold/Silver = {gs:.1f} < 65 (optimismo)")

    # Cobre
    if copper is not None and len(copper) > 200:
        copper_above = float(copper["close"].iloc[-1] > copper["close"].rolling(200).mean().iloc[-1])
        if copper_above:
            score += 0.5
            assessment["signals"].append("Cobre sobre MA200 (expansión)")
        else:
            score -= 0.5
            assessment["signals"].append("Cobre bajo MA200 (contracción)")

    # SPY momentum
    if spy is not None and len(spy) > 50:
        spy_ret = float(spy["close"].pct_change(50).iloc[-1] * 100)
        if spy_ret > 5:
            score += 0.5
            assessment["signals"].append(f"S&P 500 +{spy_ret:.1f}% en 50d")
        elif spy_ret < -5:
            score -= 0.5
            assessment["signals"].append(f"S&P 500 {spy_ret:.1f}% en 50d")

    if score >= 1.5:
        assessment["regime"] = "RISK_ON_FUERTE"
    elif score >= 0.5:
        assessment["regime"] = "RISK_ON"
    elif score <= -1.5:
        assessment["regime"] = "RISK_OFF_FUERTE"
    elif score <= -0.5:
        assessment["regime"] = "RISK_OFF"
    else:
        assessment["regime"] = "NEUTRAL"

    assessment["score"] = round(score, 2)
    return assessment
