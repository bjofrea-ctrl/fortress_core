"""API routes para el motor predictivo Fortress Core Fase 2."""
from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool
from typing import Optional
import pandas as pd
import os

from app.core.data_ingestion import download_data
from app.core.predictive_engine import PredictiveEngine, format_recommendation
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.indicators import calculate_all_indicators
from app.core.edgar_fundamentals import get_fundamentals, SAMPLE_FUNDAMENTALS
from app.core.fundamentals_client import FinnhubClient
from app.utils.logging import logger

_finnhub_client = FinnhubClient()

router = APIRouter(prefix="/api/predict", tags=["predict"])

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

# Datos de predicción (Polymarket-like) — valores de ejemplo actualizables
SAMPLE_PREDICTION_DATA = {
    "recession_prob": 0.22,      # Probabilidad de recesión en 12 meses
    "fed_cut_prob": 0.75,        # Probabilidad de recorte de tasas en 2025
    "inflation_prob": 0.15,      # Probabilidad de inflación > 4%
    "default_prob": 0.05,        # Probabilidad de default EEUU
    "unemployment_prob": 0.18,   # Probabilidad de desempleo > 5%
}


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
    """Serializa PredictionResult a dict para JSON."""
    return {
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
        "confidence": result.confidence,
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


@router.get("/analyze/{symbol}")
async def analyze_symbol(symbol: str, regime_state: int = Query(0, ge=0, le=3)):
    """Analiza un símbolo con el motor predictivo completo."""
    try:
        # Cargar datos del símbolo
        df = download_data(symbol, "2015-01-01")
        if len(df) < 200:
            raise HTTPException(status_code=404, detail=f"Datos insuficientes para {symbol}")

        # Cargar datos macro
        macro_data = _load_macro_data()

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
            prediction_data=SAMPLE_PREDICTION_DATA,
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
    """Analiza todos los símbolos disponibles y los rankea."""
    if not os.path.exists(CACHE_DIR):
        return {"symbols": [], "error": "No hay datos en cache"}

    files = [f.replace(".parquet", "") for f in os.listdir(CACHE_DIR) if f.endswith(".parquet")]
    engine = PredictiveEngine()
    macro_data = _load_macro_data()
    sentiment_data = _load_sentiment_data()
    results = []

    for symbol in sorted(files):
        try:
            df = download_data(symbol, "2015-01-01")
            if len(df) < 200:
                continue

            fundamentals = get_fundamentals_api(symbol)
            result = await run_in_threadpool(
                engine.analyze,
                symbol=symbol.upper(),
                df=df,
                regime_state=regime_state,
                fundamentals=fundamentals,
                macro_data=macro_data,
                prediction_data=SAMPLE_PREDICTION_DATA,
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
        macro_data = _load_macro_data()
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