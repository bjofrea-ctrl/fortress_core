"""Persistencia de sugerencias emitidas por el dashboard (Pieza 2).

Track record honesto: cada sugerencia emitida por /api/opportunities/today se
guarda con su score y win_prob; la evaluación a CALIBRATION_HORIZON_DAYS días
hábiles se marca con el resultado real (mismo patrón que record_prediction).
El scoreboard del dashboard se construye SOLO con estos datos reales.

Formato: JSON simple en data/cache/suggestions.json (decisión acordada —
hay infraestructura de parquet/JSON en data/cache, no requiere DB).
"""
import json
import os
from typing import Dict, List

import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
SUGGESTIONS_PATH = os.path.join(CACHE_DIR, "suggestions.json")

CALIBRATION_HORIZON_DAYS = 20


def _load() -> List[Dict]:
    if not os.path.exists(SUGGESTIONS_PATH):
        return []
    try:
        with open(SUGGESTIONS_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(suggestions: List[Dict]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(SUGGESTIONS_PATH, "w") as f:
        json.dump(suggestions, f, indent=2, default=str)


def record_suggestions(suggestions: List[Dict], as_of: str) -> int:
    """Registra las sugerencias del día. Dedup por (symbol, fecha): no se
    re-registra una sugerencia ya emitida el mismo día (el job diario puede
    llamar dos veces). Devuelve cuántas nuevas se agregaron."""
    store = _load()
    existing = {(s["symbol"], str(s["date"])) for s in store}
    added = 0
    for sug in suggestions:
        key = (sug["symbol"], as_of)
        if key in existing:
            continue
        store.append({
            "symbol": sug["symbol"],
            "date": as_of,
            "score": sug.get("score"),
            "win_prob": sug.get("win_prob"),
            "outcome": None,
            "evaluated_at": None,
        })
        existing.add(key)
        added += 1
    if added:
        _save(store)
    return added


def evaluate_pending(price_data: Dict[str, pd.DataFrame]) -> Dict:
    """Evalúa sugerencias vencidas: una sugerencia se marca con el resultado
    real si pasaron CALIBRATION_HORIZON_DAYS días hábiles desde su emisión
    (entry = close del día de la sugerencia, outcome = close en entry + N
    días hábiles, mismo contrato que _build_calibration_dataset: won =
    future > entry). Devuelve {evaluated: n, remaining: n}."""
    store = _load()
    if not store:
        return {"evaluated": 0, "remaining": 0}

    pending = [s for s in store if s.get("outcome") is None]
    evaluated = 0
    for sug in pending:
        df = price_data.get(sug["symbol"])
        if df is None or "close" not in df.columns:
            continue
        dates = df.index
        try:
            entry_date = pd.Timestamp(sug["date"])
        except (TypeError, ValueError):
            continue
        if entry_date not in dates:
            # buscar la fecha de trading más cercana >= a la emisión
            later = dates[dates >= entry_date]
            if len(later) == 0:
                continue
            entry_date = later[0]
        pos = dates.get_loc(entry_date)
        if pos + CALIBRATION_HORIZON_DAYS >= len(dates):
            continue  # aún no vence
        entry_price = float(df["close"].iloc[pos])
        future_price = float(df["close"].iloc[pos + CALIBRATION_HORIZON_DAYS])
        sug["outcome"] = 1 if future_price > entry_price else 0
        sug["evaluated_at"] = str(pd.Timestamp(dates[pos + CALIBRATION_HORIZON_DAYS]).date())
        evaluated += 1

    if evaluated:
        _save(store)
    return {"evaluated": evaluated, "remaining": sum(1 for s in store if s.get("outcome") is None)}


def get_track_record() -> Dict:
    """Scoreboard honesto: métricas sobre las sugerencias YA evaluadas.
    Solo se reportan n >= 5 (con menos, el win_rate no es interpretable)."""
    store = [s for s in _load() if s.get("outcome") is not None]
    total = len(store)
    if total < 5:
        return {"n": total, "sufficient": False,
                "note": "Menos de 5 sugerencias evaluadas — win_rate aún no interpretable"}

    wins = sum(1 for s in store if s["outcome"] == 1)
    probs = [s["win_prob"] for s in store if s.get("win_prob") is not None]
    brier = None
    if len(probs) == total:
        brier = round(sum((p - o) ** 2 for p, o in zip(probs, [s["outcome"] for s in store])) / total, 4)
    return {
        "n": total,
        "sufficient": True,
        "win_rate": round(wins / total, 4),
        "wins": wins,
        "losses": total - wins,
        "brier": brier,
        "horizon_days": CALIBRATION_HORIZON_DAYS,
        "note": "Solo sugerencias emitidas por el dashboard, evaluadas a 20 días hábiles",
    }
