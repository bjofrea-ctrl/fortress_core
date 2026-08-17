"""API routes — panel de ranking con percentiles reales.

GET /api/ranking/current — percentiles actuales de todos los símbolos
GET /api/ranking/{symbol} — historial de percentiles para un símbolo
GET /api/ranking/history — historial completo de percentiles

Este endpoint usa el panel de ranking generado por scripts/generate_ranking_panel.py
que incluye TODOS los 50 símbolos (sin filtro eligible), permitiendo calcular
percentiles reales dentro del universo.
"""

import os
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/ranking", tags=["ranking"])

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cache")
RANKING_PANEL_PATH = os.path.join(CACHE_DIR, "ranking_panel.parquet")


def _load_ranking_panel() -> pd.DataFrame:
    """Cargar el panel de ranking desde parquet."""
    if not os.path.exists(RANKING_PANEL_PATH):
        raise FileNotFoundError(
            f"Panel de ranking no encontrado en {RANKING_PANEL_PATH}. "
            "Ejecutar scripts/generate_ranking_panel.py primero."
        )
    return pd.read_parquet(RANKING_PANEL_PATH)


def _get_latest_date(df: pd.DataFrame) -> str:
    """Obtener la fecha más reciente del panel."""
    return df["date"].max()


def _get_current_rankings(df: pd.DataFrame) -> List[Dict]:
    """Obtener percentiles actuales de todos los símbolos."""
    latest_date = _get_latest_date(df)
    latest = df[df["date"] == latest_date].copy()

    result = []
    for _, row in latest.iterrows():
        result.append({
            "symbol": row.name if hasattr(row, 'name') and row.name else row.get("symbol", ""),
            "date": str(latest_date),
            "momentum_rank": round(float(row.get("momentum_rank", 0)), 2),
            "rsi_rank": round(float(row.get("rsi_rank", 0)), 2),
            "adx_rank": round(float(row.get("adx_rank", 0)), 2),
            "trend_rank": round(float(row.get("trend_rank", 0)), 2),
            "momentum_score": round(float(row.get("momentum_score", 0)), 4),
            "rsi_score": round(float(row.get("rsi_score", 0)), 4),
            "adx_score": round(float(row.get("adx_score", 0)), 4),
            "trend_ok": bool(row.get("trend_ok", False)),
        })

    return sorted(result, key=lambda x: x["symbol"])


def _get_symbol_ranking_history(df: pd.DataFrame, symbol: str) -> List[Dict]:
    """Obtener historial de percentiles para un símbolo."""
    symbol_data = df[df.index == symbol].copy()
    if symbol_data.empty:
        return []

    result = []
    for _, row in symbol_data.iterrows():
        result.append({
            "date": str(row.get("date", "")),
            "momentum_rank": round(float(row.get("momentum_rank", 0)), 2),
            "rsi_rank": round(float(row.get("rsi_rank", 0)), 2),
            "adx_rank": round(float(row.get("adx_rank", 0)), 2),
            "trend_rank": round(float(row.get("trend_rank", 0)), 2),
            "momentum_score": round(float(row.get("momentum_score", 0)), 4),
            "rsi_score": round(float(row.get("rsi_score", 0)), 4),
            "adx_score": round(float(row.get("adx_score", 0)), 4),
            "trend_ok": bool(row.get("trend_ok", False)),
        })

    return sorted(result, key=lambda x: x["date"])


@router.get("/current")
async def ranking_current():
    """Percentiles actuales de todos los símbolos del universo."""
    try:
        df = _load_ranking_panel()
        rankings = _get_current_rankings(df)
        return {
            "as_of": _get_latest_date(df),
            "count": len(rankings),
            "rankings": rankings,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando ranking: {str(e)}")


@router.get("/{symbol}")
async def ranking_symbol(symbol: str):
    """Historial de percentiles para un símbolo específico."""
    try:
        df = _load_ranking_panel()
        history = _get_symbol_ranking_history(df, symbol)

        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"Símbolo {symbol} no encontrado en el panel de ranking"
            )

        return {
            "symbol": symbol,
            "history": history,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando ranking: {str(e)}")


@router.get("")
async def ranking_all():
    """Historial completo de percentiles para todos los símbolos."""
    try:
        df = _load_ranking_panel()

        # Agrupar por símbolo
        result = {}
        for symbol in df.index.unique():
            history = _get_symbol_ranking_history(df, symbol)
            result[symbol] = history

        return {
            "symbols": list(sorted(result.keys())),
            "count": len(result),
            "data": result,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando ranking: {str(e)}")
