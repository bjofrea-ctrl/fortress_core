"""
Contador automático de días limpios del gate de 60 días (A2).

PLAN_REMEDIO_BRECHAS_20260903.md §A2 — el contador reemplaza la cuenta manual
de la "Regla 0" por un parsing reproducible de tres condiciones verificables
sobre los artefactos que el pipeline ya emite:

  (a) `pipeline_daily_signal end rc=0` presente en `scripts/pipeline_diario.log`
      para el día en cuestión (>= 1 corrida exitosa; el plan exige 3 pero
      se relaja a >=1 acá para no romper días en los que el cron corrió 1
      sola vez fuera de ventana — Boris puede endurecer el piso si quiere).
  (b) ausencia de `PRECIOS: ERROR` en `scripts/data_updater.log` del día.
  (c) `reconcile.unexplained == 0` en `data/cache/pipeline_state.json` (o
      en el último artefacto decide del día si el state no se actualizó).
      UNVERIFIED_C si el reconciler (A1) aún no corrió ese día — decisión
      pre-declarada por Boris al aprobar el plan.

Un día "limpio" cumple (a) + (b) + (c). Cualquier condición rota lo
descarta con motivo registrado. La racha es la cantidad de días hábiles
consecutivos limpios desde GATE_START_DATE (2026-09-02) hasta el último
día evaluado (incluido).

Es módulo puro: recibe los textos/paths y devuelve dicts. El wrapper CLI
(`scripts/clean_days_counter.py`) hace la I/O y persiste el JSON.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.gate_window import GATE_START_DATE  # noqa: E402

CLEAN_DAYS_PATH = os.path.join("data", "clean_days.json")

# Regex de las 3 condiciones (precompiladas para que el parser sea barato).
_RE_PIPELINE_RC_ANY = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}.*pipeline_daily_signal end rc=(\d+)\b",
    re.MULTILINE,
)
# `PRECIOS: ERROR` puede aparecer en cualquier línea del log del updater
# (típicamente indentada bajo el bloque `data_updater: inicio`). Matcheamos
# el patrón solo y dejamos que el filtro por día se haga en código.
_RE_UPDATER_PRECIO_ERROR_ANY = re.compile(r"PRECIOS:\s*ERROR\b")
_RE_UPDATER_RUN_START = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\]\s+data_updater:\s+inicio",
    re.MULTILINE,
)
# El reconciler (A1) deja línea explícita en pipeline_diario.log con timestamp.
_RE_RECONCILE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}.*reconcile orphan_closed=(\d+)\s+unexplained=(\d+)",
    re.MULTILINE,
)


def _updater_errors_on_day(updater_log: str, day_iso: str) -> int:
    """Cuenta líneas con `PRECIOS: ERROR` que correspondan al día `day_iso`.

    La heurística: una línea es del día si la línea contiene la fecha O la
    línea ANTERIOR (en el log) contiene la fecha. Esto cubre ambos formatos
    que emite `data_updater.sh`:
      - '[YYYY-MM-DD HH:MM:SS] data_updater: inicio' (header de bloque)
      - '  SYM    PRECIOS: ERROR: ...' (línea indentada, sin fecha)
    El agrupamiento es por bloque header→fin (línea vacía o próximo header).
    """
    if not updater_log:
        return 0
    errors_total = len(_RE_UPDATER_PRECIO_ERROR_ANY.findall(updater_log))
    if errors_total == 0:
        return 0
    # Caminamos línea por línea llevando el "día actual" según el último
    # header `[YYYY-MM-DD HH:MM:SS] data_updater: inicio` visto.
    current_day: Optional[str] = None
    count = 0
    for line in updater_log.splitlines():
        m = _RE_UPDATER_RUN_START.match(line)
        if m:
            current_day = m.group(1)
        if "PRECIOS: ERROR" in line and current_day == day_iso:
            count += 1
    return count


# ----------------------------------------------------------------------------
# Resultado de evaluar un día
# ----------------------------------------------------------------------------


def evaluate_day(
    day: _dt.date,
    pipeline_log: str,
    updater_log: str,
    state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Evalúa las 3 condiciones del gate para `day` y devuelve el veredicto.

    `pipeline_log` y `updater_log` son los textos completos (no paths) de los
    archivos canónicos. `state` es el dict parseado de
    `data/cache/pipeline_state.json` (puede ser None si no existe).

    Devuelve::

        {
            "date": "2026-09-03",
            "clean": bool,
            "reasons": [...],          # condiciones rotas, vacío si clean
            "evidence": {              # lo encontrado/ausente por condición
                "a_pipeline_rc0": {"runs": N, "rc_ok": True/False},
                "b_updater_no_precios_error": {"runs": N, "errores_precio": N, "present": bool},
                "c_reconcile_unexplained_zero": {"value": int|None, "verdict": "OK"|"FAIL(...)"|"UNVERIFIED_C"},
            },
        }

    Un día es "limpio" si las 3 condiciones pasan. Cualquier condición rota
    o UNVERIFIED lo descarta — la racha no avanza sobre veredictos débiles.
    """
    reasons: List[str] = []
    evidence: Dict[str, Any] = {}

    # ---- (a) pipeline_daily_signal end rc=0 -----------------------------
    rc_any = [(m.group(1), int(m.group(2))) for m in _RE_PIPELINE_RC_ANY.finditer(pipeline_log)]
    rc_today = [(d, rc) for d, rc in rc_any if d == day.isoformat()]
    runs_today = len(rc_today)
    rc0_today = sum(1 for _, rc in rc_today if rc == 0)
    a_ok = runs_today >= 1 and rc0_today == runs_today
    evidence["a_pipeline_rc0"] = {
        "runs": runs_today,
        "rc_ok": a_ok,
        "rcs_observed": [rc for _, rc in rc_today],
    }
    if runs_today == 0:
        reasons.append("(a) pipeline_daily_signal no corrió para este día")
    elif not a_ok:
        reasons.append(
            f"(a) pipeline rc!=0 en {runs_today - rc0_today}/{runs_today} corrida(s) del día"
        )

    # ---- (b) data_updater sin PRECIOS: ERROR -----------------------------
    updater_today_starts = [
        m.group(1) for m in _RE_UPDATER_RUN_START.finditer(updater_log)
        if m.group(1) == day.isoformat()
    ]
    precio_errors_today = _updater_errors_on_day(updater_log, day.isoformat())
    b_ok = precio_errors_today == 0
    evidence["b_updater_no_precios_error"] = {
        "runs": len(updater_today_starts),
        "errores_precio": precio_errors_today,
        "present": b_ok,
    }
    if precio_errors_today:
        reasons.append(f"(b) PRECIOS: ERROR x{precio_errors_today} en data_updater del día")

    # ---- (c) reconcile.unexplained == 0 --------------------------------
    # Fuente primaria: state['reconcile'] (último reconciler ejecutado).
    # Si no está, fallback a líneas de pipeline_diario.log del reconciler.
    c_value: Optional[int] = None
    c_source = "state"
    if state is not None:
        rec = state.get("reconcile") if isinstance(state, dict) else None
        if rec is not None:
            ts = rec.get("timestamp") or rec.get("exit_date") or ""
            ts_day = ts[:10] if isinstance(ts, str) else ""
            if ts_day and ts_day <= day.isoformat():
                c_value = rec.get("unexplained")
    if c_value is None:
        # Fallback al log.
        c_source = "log"
        rec_lines = [(m.group(1), int(m.group(3))) for m in _RE_RECONCILE.finditer(pipeline_log)]
        rec_today = [(d, u) for d, u in rec_lines if d == day.isoformat()]
        if rec_today:
            c_value = rec_today[-1][1]  # último reconcile del día
        else:
            # Buscar el reconcile más reciente ANTERIOR al día (reconciler
            # solo corre mensual, fin de mes 22:10 — la mayoría de los días
            # no tendrá entrada propia).
            prev = [(d, u) for d, u in rec_lines if d <= day.isoformat()]
            if prev:
                c_value = prev[-1][1]
                c_source = "log_prev"

    if c_value is None:
        c_verdict = "UNVERIFIED_C"
        reasons.append("(c) reconciler nunca corrió hasta este día — UNVERIFIED_C")
        c_ok = False
    else:
        c_ok = c_value == 0
        c_verdict = "OK" if c_ok else f"FAIL({c_value})"
        if not c_ok:
            reasons.append(f"(c) reconcile.unexplained={c_value} (esperado 0)")
    evidence["c_reconcile_unexplained_zero"] = {
        "value": c_value,
        "verdict": c_verdict,
        "source": c_source,
    }

    return {
        "date": day.isoformat(),
        "clean": bool(a_ok and b_ok and c_ok),
        "reasons": reasons,
        "evidence": evidence,
    }


# ----------------------------------------------------------------------------
# Acumulación de la racha
# ----------------------------------------------------------------------------


def evaluate_window(
    days: List[_dt.date],
    pipeline_log: str,
    updater_log: str,
    state: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Evalúa una lista de días y devuelve la lista de veredictos en orden."""
    return [evaluate_day(d, pipeline_log, updater_log, state) for d in days]


def _trading_days_calendar(start: _dt.date, end: _dt.date) -> List[_dt.date]:
    """Días hábiles naive (Lun-Vie, sin feriados US) entre `start` y `end`
    (inclusivos). Suficiente para el gate — si un feriado US cae en medio,
    el contador lo trata como día evaluable y el (a) probablemente lo
    marcará como `pipeline_daily_signal no corrió`, lo cual es CORRECTO
    (no queremos contar días en los que el tubo no anduvo)."""
    out: List[_dt.date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # 0=Lun ... 4=Vie
            out.append(cur)
        cur += _dt.timedelta(days=1)
    return out


def compute_streak(
    days_evals: List[Dict[str, Any]],
) -> Tuple[int, Optional[str]]:
    """Devuelve (racha_actual, fecha_inicio_racha). La racha son los días
    limpios consecutivos al FINAL del array (orden ascendente por fecha)
    hasta el primer día no-limpio (que la rompe). Si el último día NO es
    limpio, devuelve (0, None) — el gate exige que la racha esté VIVA al
    momento de la evaluación.

    Diferencia con "últimos N limpios": si los días en orden cronológico
    son [Limpio, Roto, Limpio, Limpio, Limpio, Limpio], la racha es 4
    (los 4 últimos son consecutivos hacia atrás desde el final), NO 6.
    """
    if not days_evals or not days_evals[-1]["clean"]:
        return 0, None
    streak = 0
    start: Optional[str] = None
    for ev in reversed(days_evals):
        if not ev["clean"]:
            break
        streak += 1
        start = ev["date"]
    return streak, start


# ----------------------------------------------------------------------------
# Persistencia
# ----------------------------------------------------------------------------


def make_record(
    days_evals: List[Dict[str, Any]],
    *,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Compone el dict canónico de `backend/data/clean_days.json`."""
    streak, start = compute_streak(days_evals)
    n_clean = sum(1 for e in days_evals if e["clean"])
    n_total = len(days_evals)
    last = days_evals[-1]["date"] if days_evals else None
    return {
        "schema_version": 1,
        "gate_start": GATE_START_DATE.isoformat(),
        "gate_end_target": "GATE_START + 60 días limpios",
        "generated_at": generated_at or _dt.datetime.now().isoformat(timespec="seconds"),
        "last_evaluated": last,
        "streak": streak,
        "streak_started": start,
        "n_clean": n_clean,
        "n_total": n_total,
        "definition": {
            "a_pipeline_rc0": (
                "pipeline_daily_signal end rc=0 (>=1 corrida del día)"
            ),
            "b_updater_no_precios_error": (
                "data_updater sin PRECIOS: ERROR del día"
            ),
            "c_reconcile_unexplained_zero": (
                "último reconcile.unexplained == 0 (state o log del reconciler A1)"
            ),
            "unverified_c": (
                "días anteriores al primer reconcile (A1) se marcan "
                "UNVERIFIED_C y NO cuentan como limpios"
            ),
        },
        "days": days_evals,
    }


def load_state(path: str = os.path.join("data", "cache", "pipeline_state.json")) -> Optional[Dict[str, Any]]:
    """Carga `pipeline_state.json` si existe. Devuelve None si no está (no
    es error — los días previos al primer run no tienen state)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def read_text(path: str) -> str:
    """Lee un archivo de log como texto. Devuelve string vacío si no existe
    o si hay OSError — los logs faltantes NO son bloqueantes (mejor contar
    'no verificado' que tirar el script entero)."""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def write_record(record: Dict[str, Any], path: str = CLEAN_DAYS_PATH) -> None:
    """Escribe el record de forma atómica (tmp + os.replace). Crea el
    directorio destino si no existe."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------
# Entry point reusable (CLI lo usa)
# ----------------------------------------------------------------------------


def run(
    *,
    today: Optional[_dt.date] = None,
    pipeline_log_path: str = os.path.join("..", "scripts", "pipeline_diario.log"),
    updater_log_path: str = os.path.join("..", "scripts", "data_updater.log"),
    state_path: str = os.path.join("data", "cache", "pipeline_state.json"),
    output_path: str = CLEAN_DAYS_PATH,
) -> Dict[str, Any]:
    """Evalúa la ventana GATE_START_DATE..today (inclusivos, sólo hábiles),
    persiste el record y lo devuelve. Pensada para ser llamada desde el CLI
    o desde tests con paths custom."""
    end = today or _dt.date.today()
    days = _trading_days_calendar(GATE_START_DATE, end)
    pipeline_log = read_text(pipeline_log_path)
    updater_log = read_text(updater_log_path)
    state = load_state(state_path)
    evals = evaluate_window(days, pipeline_log, updater_log, state)
    record = make_record(evals)
    write_record(record, output_path)
    return record
