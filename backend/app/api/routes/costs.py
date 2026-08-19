"""API routes — costos de ejecución medidos (M4).

Tarea E (PLAN_LARGO_PLAZO.md, Ronda 2026-08-19): el dashboard necesita un campo
de costo REAL — el número asumido (`settings.COST_PER_SIDE = 0.0015`) vive en el
motor, pero la medición M4 (Alpaca paper, 2026-08-18) ya produjo el primer punto
real: `cost_per_side_medido ≈ 0.000189` (≈0.019% por lado).

GET /api/costs/current — SOLO LECTURA. Lee el registro canónico
(`execution_costs.db`, SQLite de `app.core.execution_costs.ExecutionCostRecorder`)
y, si el archivo no existe o está vacío, el artefacto `.txt` más reciente
(`measure_execution_costs_*.txt`, que embebe el mismo contrato de salida como JSON).

CONTRATO DE HONESTIDAD (ONBOARDING #1/#4, heredado de M4): si NO hay medición
disponible, la respuesta es 200 con `"medido": false` y una nota — NUNCA se
inventa un número, y el frontend lo muestra como "sin medición".

CAVEAT permanente (registrado en ROADMAP M4): es costo de ejecución PAPER —
fills instantáneos a último trade sin comisión. Es un PISO INFERIOR medido, no
el costo live final. El número viaja con esta nota siempre.
"""
import glob
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from app.core.execution_costs import ExecutionCostRecorder, summarize

router = APIRouter(prefix="/api/costs", tags=["costs"])

# CAVEAT M4 — se adjunta a toda respuesta medido=true. Texto breve: la UI lo
# muestra como tooltip; el artefacto y el ROADMAP tienen la versión completa.
_CAVEAT_PAPER = (
    "Costo de ejecución PAPER (fills instantáneos, sin comisión real) — "
    "piso inferior medido, no costo live final."
)
_SIN_MEDICION_NOTA = (
    "No hay medición de costos ejecutada todavía (falta execution_costs.db "
    "o un artefacto measure_execution_costs_*.txt). El número no se inventa: "
    "el campo queda en 'sin medición'."
)
_ARTIFACT_GLOB = "measure_execution_costs_*.txt"


def _db_path() -> str:
    """Ruta canónica de la DB de mediciones (override por env, igual que
    `ExecutionCostRecorder`). Anclada al repo: `backend/data/cache/`."""
    env = os.environ.get("FORTRESS_COSTS_DB", "")
    if env:
        return env
    return str(Path(__file__).resolve().parents[3] / "data" / "cache" / "execution_costs.db")


def _cache_dir() -> str:
    return str(Path(__file__).resolve().parents[3] / "data" / "cache")


def _latest_artifact_path() -> Optional[str]:
    """El artefacto `.txt` más reciente de medición, si existe."""
    matches = sorted(glob.glob(os.path.join(_cache_dir(), _ARTIFACT_GLOB)))
    return matches[-1] if matches else None


def _read_artifact_summary(path: str) -> Optional[Dict[str, Any]]:
    """Extrae el bloque JSON 'RESUMEN (contrato de salida M4)' del artefacto.

    El runner de M4 embebe el mismo contrato que `summarize()` como JSON
    indentado. Si el artefacto no tiene el bloque o no parsea, devuelve None —
    nunca se adivina un número.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"RESUMEN \(contrato de salida M4\):\s*(\{.*?\})\s*=+", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return None
    required = {"cost_per_side_medido", "n_ordenes", "slippage_p50", "slippage_p95"}
    if not required.issubset(payload.keys()):
        return None
    return payload


def _load_records_from_db(db_path: str) -> List[Dict[str, Any]]:
    """Registros completos de la DB de mediciones (vacío si no hay filas).

    Una DB corrupta o ilegible NUNCA crashea el endpoint: devuelve vacío y la
    cadena cae al fallback del artefacto o a `medido: false` — jamás un 500
    con un número que no se pudo leer.
    """
    if not os.path.exists(db_path):
        return []
    try:
        recorder = ExecutionCostRecorder(db_path=db_path)
    except sqlite3.Error:
        return []
    try:
        return recorder.records()
    except sqlite3.Error:
        return []
    finally:
        recorder.close()


def _group_by_size(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Curva de costo por tamaño de orden: un resumen por `size` distinto.

    La Tarea D (Kilo Code) agrega qty=10/50 a la misma DB; el endpoint ya
    devuelve la curva completa para que el dashboard no cambie de contrato.
    Orden estable: size ascendente.
    """
    by_size: Dict[float, List[Dict[str, Any]]] = {}
    for r in records:
        by_size.setdefault(float(r["size"]), []).append(r)
    points = []
    for size in sorted(by_size):
        summary = summarize(by_size[size])
        points.append(
            {
                "size": size,
                "cost_per_side_medido": summary["cost_per_side_medido"],
                "slippage_p50": summary["slippage_p50"],
                "slippage_p95": summary["slippage_p95"],
                "n_ordenes": summary["n_ordenes"],
            }
        )
    return points


@router.get("/current")
def costs_current() -> Dict[str, Any]:
    """Última medición de costos de ejecución (M4) — nunca un número inventado.

    Fuentes en orden: DB `execution_costs.db` (registro canónico, puede tener
    la curva completa qty=1/10/50), luego artefacto `.txt` más reciente, luego
    `medido: false` con nota.
    """
    records = _load_records_from_db(_db_path())
    if records:
        summary = summarize(records)
        fecha_medicion = max(r["date"] for r in records)
        return {
            "medido": True,
            "cost_per_side_medido": summary["cost_per_side_medido"],
            "slippage_p50": summary["slippage_p50"],
            "slippage_p95": summary["slippage_p95"],
            "comision_media": summary["comision_media"],
            "n_ordenes": summary["n_ordenes"],
            "ventana": summary["ventana"],
            "fecha_medicion": fecha_medicion,
            "sizes": _group_by_size(records),
            "nota": _CAVEAT_PAPER,
        }

    artifact = _latest_artifact_path()
    if artifact:
        payload = _read_artifact_summary(artifact)
        if payload:
            m = re.search(r"(\d{8})_(\d{6})", os.path.basename(artifact))
            fecha = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}" if m else None
            return {
                "medido": True,
                "cost_per_side_medido": payload["cost_per_side_medido"],
                "slippage_p50": payload["slippage_p50"],
                "slippage_p95": payload["slippage_p95"],
                "comision_media": payload.get("comision_media", 0.0),
                "n_ordenes": int(payload["n_ordenes"]),
                "ventana": payload.get("ventana"),
                "fecha_medicion": fecha,
                "sizes": [],
                "nota": _CAVEAT_PAPER,
            }

    return {
        "medido": False,
        "cost_per_side_medido": None,
        "slippage_p50": None,
        "slippage_p95": None,
        "comision_media": None,
        "n_ordenes": 0,
        "ventana": None,
        "fecha_medicion": None,
        "sizes": [],
        "nota": _SIN_MEDICION_NOTA,
    }
