"""Contador de días limpios AUTOMÁTICO (A2 — PLAN_REMEDIO_BRECHAS_20260903 §A2).

Remplaza el conteo manual de la "Regla 0" del gate (ROADMAP.md, definición
fijada 2026-09-02 ANTES de que haga falta). Un día hábil cuenta como LIMPIO
si Y SOLO SI las 3 condiciones se cumplen ese día:

  (a) ``pipeline_diario.log`` muestra ``rc=0`` en sus 3 corridas programadas
      (ventanas 09:35 / 15:40 / 22:10 ET — los bloques ``pipeline_daily_signal
      <fecha> <hora> start`` … ``pipeline_daily_signal end rc=N``).
  (b) ``data_updater.log`` sin línea ``PRECIOS: ERROR`` en la corrida del día
      (bloques delimitados por ``Corrida <timestamp>`` / cierre
      ``data_updater: fin``).
  (c) el reconciler (A1) corrió sin dejar posiciones inexplicadas:
      ``reconcile orphan_closed=N unexplained=0`` en ``pipeline_diario.log``
      con timestamp del día, o ``state['reconcile']['unexplained'] == 0``
      en ``pipeline_state.json``.

Un día que falla cualquiera de las 3 NO cuenta — y NO rompe la racha
retroactivamente: solo no suma (definición del gate, palabra de Boris).

Semántica de racha (corriente ininterrumpida de días limpios CONSECUTIVOS
en días hábiles): un día hábil verificado y no-limpio corta la racha; un
día no-hábil (fin de semana: no hay corrida del updater) no la corta.

Días previos al arranque real del reconciler A1 (deploy 2026-09-04,
commit f7281d0): la condición (c) no es verificable — quedan marcados
``UNVERIFIED_C`` (decisión pre-declarada por Boris al aprobar el plan;
ver PLAN_REMEDIO_BRECHAS_20260903.md §A2). Un día UNVERIFIED_C tampoco
suma, pero no corta la racha retroactivamente de lo verificado después.

Día hábil = día de semana (Lun-Vie) con corrida del updater presente (el
gate corre sobre el calendario del propio sistema, no de feriados US).

Salida: ``backend/data/clean_days.json`` — racha actual + tabla por día
con la evidencia de cada condición (para auditoría: el JSON muestra el
PORQUÉ de cada día). Corre al final de la fase 22:10 (daily_signal_pipeline
lo invoca tras pipeline_daily_signal; ver scripts/daily_signal_pipeline.sh).

Funciones PURAS (sin I/O) para todo el parseo/evaluación — testeables con
fixtures sintéticos; las rutas de disco son parámetros con defaults
relativos a cwd=backend (mismo patrón que pipeline_daily_signal.py).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from typing import Dict, List, Optional

# ---- Rutas (relativas a cwd=backend, patrón del resto del módulo) ----
# El pipeline corre con cd backend (daily_signal_pipeline.sh); NUNCA __file__
# (resolvería a backend/scripts/, que no es el cwd de la shell).
REPO_ROOT = os.path.join("..")
PIPELINE_LOG = os.path.join(REPO_ROOT, "scripts", "pipeline_diario.log")
UPDATER_LOG = os.path.join(REPO_ROOT, "scripts", "data_updater.log")
STATE_PATH = os.path.join("data", "cache", "pipeline_state.json")
OUT_PATH = os.path.join("data", "clean_days.json")

# Arranque real del reconciler A1 en producción (commit f7281d0,
# 2026-09-04 18:39 ET). Días hábiles anteriores no pueden verificar (c).
RECONCILER_START = dt.date(2026, 9, 4)

# Ventanas programadas de la shell (hour_ET): 09:35, 15:40, 22:10. El
# contador exige rc=0 en UNA corrida por ventana (las corridas fuera de
# ventana —health manual, kickstart— no cuentan para (a), pero una
# corrida en ventana con rc!=0 SÍ rompe la condición).
SCHEDULED_WINDOWS = {9, 15, 22}

# ---- Regex de los formatos de línea (verificados contra logs reales) ----
_RE_PIPELINE_START = re.compile(
    r"^pipeline_daily_signal (\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2}) start \(hour_ET=(\d+)\)"
)
_RE_PIPELINE_END = re.compile(r"^pipeline_daily_signal end rc=(\d+)")
_RE_RECONCILE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2} \[pipeline\] reconcile "
    r"orphan_closed=(\d+) unexplained=(\d+)"
)
_RE_UPDATER_CORRIDA = re.compile(r"^Corrida (\d{4})-(\d{2})-(\d{2})T")
_RE_UPDATER_FIN = re.compile(r"data_updater: fin")


# --------------------------------------------------------------------------
# Condición (a) — rc=0 en las 3 corridas programadas del pipeline
# --------------------------------------------------------------------------

def parse_pipeline_runs(text: str) -> Dict[str, Dict[int, int]]:
    """Parsea pipeline_diario.log → {fecha: {hour_ET: rc}}.

    Empareja cada ``start`` con el ``end rc=N`` que le sigue (la shell
    escribe secuencialmente; un bloque sin end no se cuenta). Por ventana
    programada queda el ÚLTIMO rc visto (re-run dentro de la ventana
    sobreescribe — cuenta el resultado final de la fase).
    Corridas fuera de ventana (hour_ET != 9/15/22) se ignoran para (a).
    """
    runs: Dict[str, Dict[int, int]] = {}
    cur_date: Optional[str] = None
    cur_hour: Optional[int] = None
    for line in text.splitlines():
        m = _RE_PIPELINE_START.match(line)
        if m:
            cur_date = m.group(1)
            cur_hour = int(m.group(5))
            continue
        m = _RE_PIPELINE_END.match(line)
        if m and cur_date is not None and cur_hour is not None:
            if cur_hour in SCHEDULED_WINDOWS:
                runs.setdefault(cur_date, {})[cur_hour] = int(m.group(1))
            cur_date, cur_hour = None, None
    return runs


def evaluar_condicion_a(runs: Dict[str, Dict[int, int]], date_str: str) -> Dict:
    """Evidencia de (a) para un día: las 3 ventanas con rc=0."""
    day = runs.get(date_str, {})
    evidence = {f"rc_{h:02d}": day.get(h) for h in sorted(SCHEDULED_WINDOWS)}
    missing = [h for h in sorted(SCHEDULED_WINDOWS) if h not in day]
    nonzero = [h for h, rc in day.items() if rc != 0]
    ok = not missing and not nonzero
    return {"ok": ok, "runs": evidence,
            "reason": "ok" if ok else (
                f"ventanas sin corrida: {missing}" if missing else f"rc!=0 en: {nonzero}")}


# --------------------------------------------------------------------------
# Condición (b) — data_updater del día sin PRECIOS: ERROR
# --------------------------------------------------------------------------

def parse_updater_days(text: str) -> Dict[str, List[str]]:
    """Parsea data_updater.log → {fecha: [líneas del bloque de esa corrida]}.

    El bloque de una corrida arranca en ``Corrida <ts>`` y las líneas de
    precios (``precios: N/M OK`` / ``PRECIOS: ERROR ...``) caen dentro.
    La clave es la FECHA del timestamp de la corrida (una corrida por día
    en producción; si hubiera varias, se concatenan — cualquier ERROR del
    día rompe (b)).
    """
    days: Dict[str, List[str]] = {}
    cur: Optional[str] = None
    for line in text.splitlines():
        m = _RE_UPDATER_CORRIDA.match(line)
        if m:
            cur = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            days.setdefault(cur, [])
            continue
        if cur is not None:
            days[cur].append(line)
            if _RE_UPDATER_FIN.search(line):
                cur = None
    return days


def evaluar_condicion_b(updater_days: Dict[str, List[str]], date_str: str) -> Dict:
    """Evidencia de (b): corrida del updater presente y sin PRECIOS: ERROR."""
    lines = updater_days.get(date_str)
    if lines is None:
        return {"ok": False, "reason": "sin corrida del updater (día no hábil o updater caído)",
                "corrida": False}
    errores = [ln.strip() for ln in lines if "PRECIOS: ERROR" in ln]
    ok = not errores
    return {"ok": ok, "corrida": True,
            "precios_ok_line": next((ln.strip() for ln in lines
                                     if ln.strip().startswith("precios:")), None),
            "reason": "ok" if ok else "; ".join(errores[:3])}


# --------------------------------------------------------------------------
# Condición (c) — reconciler sin posiciones inexplicadas
# --------------------------------------------------------------------------

def parse_reconcile_lines(text: str) -> Dict[str, List[Dict]]:
    """Parsea pipeline_diario.log → {fecha: [{orphan_closed, unexplained}]}.

    Toda línea ``reconcile orphan_closed=N unexplained=M`` con timestamp
    del pipeline_diario.log, agrupada por FECHA del timestamp (el
    reconciller corre en la fase decide y también manual; lo que importa
    es la última línea del día — unexplained es un conteo puntual).
    """
    out: Dict[str, List[Dict]] = {}
    for line in text.splitlines():
        m = _RE_RECONCILE.match(line)
        if m:
            out.setdefault(m.group(1), []).append(
                {"orphan_closed": int(m.group(2)), "unexplained": int(m.group(3))})
    return out


def evaluar_condicion_c(reconcile_by_day: Dict[str, List[Dict]],
                        state_reconcile: Optional[Dict], date_str: str,
                        reconciler_start: dt.date = RECONCILER_START) -> Dict:
    """Evidencia de (c): unexplained=0 verificado ese día.

    Prioridad de fuentes: (1) última línea ``reconcile`` del día en
    pipeline_diario.log; (2) state['reconcile'] de pipeline_state.json si
    su fecha coincide con el día evaluado (exit_date); (3) si el día es
    anterior al arranque del reconciler → ``UNVERIFIED_C`` (no suma, no
    rompe racha retroactivamente — decisión pre-declarada de Boris §A2).

    Nota: ``orphan_closed > 0`` NO rompe (c) — el reconciler cerrar
    huérfanas con pnl_r real es SU trabajo. Solo ``unexplained > 0``
    (posiciones sin explicación contable) rompe la condición.
    """
    date = dt.date.fromisoformat(date_str)
    lines = reconcile_by_day.get(date_str)
    if lines:
        last = lines[-1]
        ok = last["unexplained"] == 0
        return {"ok": ok, "source": "pipeline_diario.log",
                "orphan_closed": last["orphan_closed"],
                "unexplained": last["unexplained"],
                "reason": "ok" if ok else f"unexplained={last['unexplained']}"}
    if state_reconcile and state_reconcile.get("exit_date") == date_str:
        un = state_reconcile.get("unexplained")
        ok = un == 0
        return {"ok": ok, "source": "pipeline_state.json", "orphan_closed":
                state_reconcile.get("orphan_closed"), "unexplained": un,
                "reason": "ok" if ok else f"unexplained={un}"}
    if date < reconciler_start:
        return {"ok": False, "status": "UNVERIFIED_C",
                "reason": "día anterior al arranque del reconciler (A1, "
                          f"{reconciler_start.isoformat()}) — no verificable"}
    return {"ok": False, "status": "UNVERIFIED_C",
            "reason": "reconciler no corrió ese día (solo corre en fase decide)"}


# --------------------------------------------------------------------------
# Día hábil y evaluación por día
# --------------------------------------------------------------------------

def business_days(updater_days: Dict[str, List[str]],
                  pipeline_runs: Dict[str, Dict[int, int]]) -> List[str]:
    """Días hábiles del registro: día de semana con corrida del updater.

    La corrida del updater es la definición operativa de día hábil del
    gate (ticket A2); si el updater no corrió no hay evidencia (b) y el
    día no puede ser limpio de todos modos.
    """
    days = set(updater_days) | set(d for d in pipeline_runs
                                   if pipeline_runs[d])
    return sorted(d for d in days
                  if dt.date.fromisoformat(d).weekday() < 5)


def evaluar_dia(pipeline_runs, updater_days, reconcile_by_day,
                state_reconcile, date_str) -> Dict:
    """Evalúa las 3 condiciones de UN día y devuelve el veredicto completo."""
    a = evaluar_condicion_a(pipeline_runs, date_str)
    b = evaluar_condicion_b(updater_days, date_str)
    c = evaluar_condicion_c(reconcile_by_day, state_reconcile, date_str)
    # UNVERIFIED_C solo "no corta racha" cuando es la ÚNICA evidencia
    # faltante: (a) y (b) verificadas OK (el día probablemente era limpio,
    # simplemente el reconciler no corrió aún). Si (a) o (b) tienen
    # evidencia de FALLO, el día está verificado-roto y corta la racha
    # aunque (c) quede sin verificar.
    unverified_only_c = (c.get("status") == "UNVERIFIED_C"
                         and a["ok"] and b["ok"])
    clean = a["ok"] and b["ok"] and c["ok"]
    return {"date": date_str, "clean": clean,
            "unverified_c": unverified_only_c,
            "conditions": {"a": a, "b": b, "c": c}}


def compute_streak(days: List[Dict]) -> Dict:
    """Racha corriente: días limpios consecutivos (en hábiles) hasta hoy.

    Recorre cronológico; un día hábil verificado no-limpio corta la racha.
    UNVERIFIED_C puro (condición (c) sin correr pero (a)+(b) OK) no la
    corta — es ausencia de evidencia, no evidencia de fallo (decisión
    pre-declarada §A2: días previos al arranque del reconciler).
    """
    streak = 0
    for d in days:
        if d["clean"]:
            streak += 1
        elif not d["unverified_c"]:
            streak = 0
        # unverified_c puro: no suma, no corta
    return {"streak": streak,
            "total_clean": sum(1 for d in days if d["clean"]),
            "total_days": len(days)}


# --------------------------------------------------------------------------
# I/O — lectura de logs reales y escritura del JSON
# --------------------------------------------------------------------------

def _read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _load_state_reconcile(state_path: str) -> Optional[Dict]:
    """Lee state['reconcile'] de pipeline_state.json (None si no existe)."""
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        rec = state.get("reconcile")
        return rec if isinstance(rec, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def build_report_from_text(pipeline_log_text: str, updater_log_text: str,
                           state_reconcile: Optional[Dict],
                           reconciler_start: dt.date = RECONCILER_START) -> Dict:
    """build_report con las fuentes INYECTADAS (texto ya leído + state).

    Versión pura para tests y verificación: mismo pipeline de evaluación
    que producción sin tocar disco.
    """
    pipeline_runs = parse_pipeline_runs(pipeline_log_text)
    updater_days = parse_updater_days(updater_log_text)
    reconcile_by_day = parse_reconcile_lines(pipeline_log_text)
    days = business_days(updater_days, pipeline_runs)
    table = [evaluar_dia(pipeline_runs, updater_days, reconcile_by_day,
                         state_reconcile, d) for d in days]
    summary = compute_streak(table)
    return {
        "schema": 1,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "definicion": "día limpio = (a) rc=0 en 3 corridas programadas + "
                      "(b) updater sin PRECIOS: ERROR + (c) reconcile unexplained=0 "
                      "(ROADMAP.md, fijada 2026-09-02; ver PLAN_REMEDIO_BRECHAS_20260903.md §A2)",
        **summary,
        "days": table,
    }


def build_report(pipeline_log: str = PIPELINE_LOG,
                 updater_log: str = UPDATER_LOG,
                 state_path: str = STATE_PATH,
                 reconciler_start: dt.date = RECONCILER_START) -> Dict:
    """Construye el reporte completo (racha + tabla por día con evidencia)."""
    pipeline_text = _read(pipeline_log)
    updater_text = _read(updater_log)
    state_reconcile = _load_state_reconcile(state_path)
    return build_report_from_text(pipeline_text, updater_text,
                                   state_reconcile,
                                   reconciler_start=reconciler_start)


def save_report(report: Dict, out_path: str = OUT_PATH) -> str:
    """Escribe clean_days.json atómico (tmp + replace, patrón del proyecto)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, out_path)
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=OUT_PATH,
                        help=f"ruta del JSON de salida (default: {OUT_PATH})")
    parser.add_argument("--stdout", action="store_true",
                        help="imprime el reporte a stdout SIN escribir disco")
    parser.add_argument("--summary-only", action="store_true",
                        help="imprime solo la línea de racha (para latidos)")
    args = parser.parse_args(argv)
    report = build_report()
    if args.stdout or args.summary_only:
        text = (json.dumps(report, indent=2, ensure_ascii=False)
                if not args.summary_only else
                f"clean_days: racha={report['streak']} "
                f"limpios={report['total_clean']}/{report['total_days']}")
        print(text)
        return 0
    path = save_report(report, args.out)
    last = report["days"][-1] if report["days"] else None
    estado = ("LIMPIO" if last and last["clean"] else
              ("UNVERIFIED_C" if last and last["unverified_c"] else "NO limpio"))
    print(f"clean_days.json -> {path} | racha={report['streak']} "
          f"limpios={report['total_clean']}/{report['total_days']} "
          f"| último día ({last['date'] if last else 'n/a'}): {estado}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
