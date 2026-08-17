"""API routes — historial de decisiones por activo.

GET /api/decision/history/{symbol} — historial de estados y transiciones
para un activo específico, con fechas y razones.

GET /api/decision/history — historial completo de todos los activos
"""

import json
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/decision/history", tags=["decision"])

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cache")
DECISION_STATES_PATH = os.path.join(CACHE_DIR, "decision_states.json")


def _load_states_history() -> List[Dict]:
    """Cargar todo el historial de estados guardados."""
    if not os.path.exists(DECISION_STATES_PATH):
        return []
    try:
        with open(DECISION_STATES_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _get_symbol_history(symbol: str, history: List[Dict]) -> List[Dict]:
    """Obtener historial de un símbolo específico con fechas ordenadas."""
    symbol_history = []
    for entry in sorted(history, key=lambda e: e.get("as_of", "")):
        states = entry.get("states", {})
        if symbol in states:
            symbol_history.append({
                "as_of": entry.get("as_of", ""),
                "state": states[symbol],
            })
    return symbol_history


def _get_transitions(symbol_history: List[Dict]) -> List[Dict]:
    """Calcular transiciones entre estados consecutivos."""
    if len(symbol_history) < 2:
        return []

    transitions = []
    for i in range(1, len(symbol_history)):
        prev = symbol_history[i-1]
        curr = symbol_history[i]
        if prev["state"] != curr["state"]:
            transitions.append({
                "from": prev["state"],
                "to": curr["state"],
                "from_date": prev["as_of"],
                "to_date": curr["as_of"],
            })
    return transitions


@router.get("/{symbol}")
async def decision_history_symbol(symbol: str):
    """Historial de decisiones para un activo específico."""
    try:
        history = _load_states_history()
        symbol_history = _get_symbol_history(symbol, history)
        transitions = _get_transitions(symbol_history)

        return {
            "symbol": symbol,
            "history": symbol_history,
            "transitions": transitions,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando historial: {str(e)}")


@router.get("")
async def decision_history_all():
    """Historial completo de decisiones para todos los activos."""
    try:
        history = _load_states_history()

        # Obtener todos los símbolos únicos
        all_symbols = set()
        for entry in history:
            all_symbols.update(entry.get("states", {}).keys())

        # Construir historial por símbolo
        result = {}
        for symbol in sorted(all_symbols):
            symbol_history = _get_symbol_history(symbol, history)
            transitions = _get_transitions(symbol_history)
            result[symbol] = {
                "history": symbol_history,
                "transitions": transitions,
            }

        return {
            "symbols": list(sorted(all_symbols)),
            "history": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando historial: {str(e)}")
