"""Kill-switch por divergencia (A3 — PLAN_REMEDIO_BRECHAS_20260903).

Reglas PRE-DECLARADAS el 2026-09-03, antes de necesitarlas (mismo estándar
que la definición de día limpio — escritas antes de cualquier divergencia):

  (i)   Drawdown paper: equity por debajo del pico rastreado en > 10%.
        El pico vive en data/kill_switch_state.json (ratchet: solo sube).
  (ii)  PnL realizado diario < media − 3σ de la historia propia del ledger
        de papel (abstención con < 10 días de historia, σ=0, o sin cierres
        hoy — no se mide lo que no se puede medir).
  (iii) Fill rate < 80% de las órdenes del día (con >= 3 órdenes; con >= 1
        orden y 0 fills = ejecución rota). Fuente: execution_telemetry (A5).
  (iv)  Staleness de precios > 2 ruedas (updater muerto — patrón 15-22/ago).
        Rueda = día hábil Lun-Vie; los feriados US posteriores a la última
        barra no se descuentan (el calendario del cache no se extiende más
        allá de su propia última barra) — conservador, documentado.

Acción al disparar: escribe data/STOP_FILE (JSON con evidencia y rearme)
que la fase ENTER respeta — pausa entradas NUEVAS, NUNCA bloquea EXIT ni
reconcile. Notificación macOS (osascript) como piso (sin Telegram). Días
bajo STOP no cuentan como limpios (interrupción, por definición del gate).

Rearme: SOLO manual — rm data/STOP_FILE (y data/kill_switch_state.json si
el STOP fue por drawdown, para re-sembrar el pico con el equity vigente).
Ninguna regla se re-arma sola; si la condición persiste tras el rearme,
el siguiente chequeo vuelve a disparar.

Puntos de evaluación (pre-declarados):
  - ENTER (inicio): STOP activo -> aborta sin evaluar. Si no: (i)+(ii)+(iv)
    pre-orden (i necesita equity real -> solo ENTER, única fase que abre
    cliente antes de comprometer dinero nuevo).
  - ENTER/EXIT (fin, post-órdenes): (iii) con las órdenes recién enviadas —
    nunca deshace lo ejecutado; protege las entradas futuras.
  - HEALTH (3x/día): (ii)+(iii)+(iv) — baratas, sin cliente ni red. Un
    disparo notifica UNA vez (el STOP activo evita re-disparo).

Todas las reglas son PURAS (entradas explícitas, cero I/O) — testeables con
fixtures de cada condición; los gatherers (ledger/telemetría) reciben los
objetos por parámetro, este módulo no importa nada de app/.
"""
import json
import os
import statistics
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---- Umbrales PRE-DECLARADOS (2026-09-03) ----
DRAWDOWN_MAX = 0.10          # (i)  equity > 10% debajo del pico
PNL_N_SIGMA = 3.0            # (ii) PnL diario < media − 3σ
PNL_MIN_HISTORY_DAYS = 10    # (ii) abstención con menos historia
FILL_RATE_MIN = 0.80         # (iii) fill rate < 80%
FILL_RATE_MIN_ORDERS = 3     # (iii) con >= 3 órdenes (o 0% con >= 1)
STALENESS_MAX_RUEDAS = 2     # (iv) cache > 2 ruedas atrás

STOP_FILE_PATH = os.path.join("data", "STOP_FILE")
STATE_FILE_PATH = os.path.join("data", "kill_switch_state.json")

REARME_HINT = ("rm data/STOP_FILE (rearme manual; si el STOP fue por drawdown, "
               "borrar también data/kill_switch_state.json para re-sembrar el pico)")


# --------------------------------------------------------------------------
# Reglas puras — una por condición pre-declarada
# --------------------------------------------------------------------------

def rule_drawdown(equity: Optional[float], peak_equity: Optional[float]) -> Dict[str, Any]:
    """(i) Drawdown del paper vs pico rastreado. Abstiene sin equity/pico."""
    if equity is None or peak_equity is None or peak_equity <= 0:
        return {"rule": "drawdown", "fired": False, "abstained": True,
                "summary": "drawdown: sin equity/pico medible — abstención"}
    dd = (peak_equity - float(equity)) / float(peak_equity)
    fired = dd > DRAWDOWN_MAX
    return {"rule": "drawdown", "fired": fired, "abstained": False,
            "detail": {"equity": float(equity), "peak": float(peak_equity),
                       "drawdown": round(dd, 6)},
            "summary": f"drawdown {dd:.1%} vs pico {peak_equity:.0f}"
                       f"{' — MAYOR a 10%: STOP' if fired else ''}"}


def rule_pnl_daily(today_pnl: Optional[float], history: List[float]) -> Dict[str, Any]:
    """(ii) PnL realizado de hoy bajo media−3σ de la historia propia.

    Abstiene si: sin cierres hoy, < PNL_MIN_HISTORY_DAYS días de historia,
    o σ=0 (sin dispersión medible — no dispara por artefacto degenerado).
    """
    if today_pnl is None:
        return {"rule": "pnl_daily", "fired": False, "abstained": True,
                "summary": "pnl diario: sin cierres hoy — abstención"}
    if len(history) < PNL_MIN_HISTORY_DAYS:
        return {"rule": "pnl_daily", "fired": False, "abstained": True,
                "summary": f"pnl diario: {len(history)} días de historia"
                           f" < {PNL_MIN_HISTORY_DAYS} — abstención"}
    sigma = statistics.stdev(history)
    if sigma <= 0:
        return {"rule": "pnl_daily", "fired": False, "abstained": True,
                "summary": "pnl diario: σ=0 (historia sin dispersión) — abstención"}
    mean = statistics.fmean(history)
    threshold = mean - PNL_N_SIGMA * sigma
    fired = float(today_pnl) < threshold
    return {"rule": "pnl_daily", "fired": fired, "abstained": False,
            "detail": {"today_pnl": float(today_pnl), "mean": round(mean, 6),
                       "sigma": round(sigma, 6),
                       "threshold": round(threshold, 6)},
            "summary": f"pnl diario {today_pnl:+.4f}R vs umbral {threshold:+.4f}R"
                       f" (media {mean:+.4f} − {PNL_N_SIGMA:g}σ)"
                       f"{' — DEBAJO: STOP' if fired else ''}"}


def rule_fill_rate(n_total: int, n_filled: int) -> Dict[str, Any]:
    """(iii) Fill rate del día. Abstiene sin órdenes; 0% con >=1 orden dispara."""
    if n_total <= 0:
        return {"rule": "fill_rate", "fired": False, "abstained": True,
                "summary": "fill rate: sin órdenes hoy — abstención"}
    rate = n_filled / n_total
    broken_all = n_filled == 0
    fired = (n_total >= FILL_RATE_MIN_ORDERS and rate < FILL_RATE_MIN) or broken_all
    return {"rule": "fill_rate", "fired": fired, "abstained": False,
            "detail": {"n_total": n_total, "n_filled": n_filled,
                       "rate": round(rate, 4)},
            "summary": f"fill rate {rate:.0%} ({n_filled}/{n_total})"
                       f"{' — EJECUCIÓN ROTA: STOP' if fired else ''}"}


def rule_staleness(ruedas_stale: Optional[int]) -> Dict[str, Any]:
    """(iv) Cache de precios más de 2 ruedas atrás (updater muerto)."""
    if ruedas_stale is None:
        return {"rule": "staleness", "fired": False, "abstained": True,
                "summary": "staleness: calendario no disponible — abstención"}
    fired = ruedas_stale > STALENESS_MAX_RUEDAS
    return {"rule": "staleness", "fired": fired, "abstained": False,
            "detail": {"ruedas_stale": ruedas_stale},
            "summary": f"cache {ruedas_stale} rueda(s) atrás"
                       f"{' — > 2: updater muerto, STOP' if fired else ''}"}


# --------------------------------------------------------------------------
# Combinadores (veredictos)
# --------------------------------------------------------------------------

def _verdict(rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    fired = [r for r in rules if r["fired"]]
    return {"stopped": bool(fired), "fired": fired, "evaluated": rules}


def evaluate_pre_order(equity: Optional[float], peak_equity: Optional[float],
                       today_pnl: Optional[float], pnl_history: List[float],
                       ruedas_stale: Optional[int]) -> Dict[str, Any]:
    """Reglas evaluables ANTES de enviar órdenes: (i)+(ii)+(iv)."""
    return _verdict([
        rule_drawdown(equity, peak_equity),
        rule_pnl_daily(today_pnl, pnl_history),
        rule_staleness(ruedas_stale),
    ])


def evaluate_fill_rate(n_total: int, n_filled: int) -> Dict[str, Any]:
    """Regla (iii) aislada — post-órdenes del día."""
    return _verdict([rule_fill_rate(n_total, n_filled)])


def evaluate_health(today_pnl: Optional[float], pnl_history: List[float],
                    n_total: int, n_filled: int,
                    ruedas_stale: Optional[int]) -> Dict[str, Any]:
    """Reglas baratas de HEALTH (sin cliente/red): (ii)+(iii)+(iv)."""
    return _verdict([
        rule_pnl_daily(today_pnl, pnl_history),
        rule_fill_rate(n_total, n_filled),
        rule_staleness(ruedas_stale),
    ])


# --------------------------------------------------------------------------
# Gatherers — leen los objetos de app/ pasados por parámetro
# --------------------------------------------------------------------------

def daily_pnls_from_ledger(ledger, today_iso: str) -> Tuple[Optional[float], List[float]]:
    """PnL REALIZADO por día (suma de pnl_r de cierres) del ledger de papel.

    Solo filas de papel (status='closed' y open_fill_price NOT NULL —
    estructural: las filas de labeling del backtest no llevan fill de
    apertura). Devuelve (suma_de_hoy|None, [sumas de días previos]). None si
    hoy no hubo cierres (día sin actividad realizada — no mide).
    """
    if ledger is None:
        return None, []
    try:
        rows = ledger.fetch()
    except Exception:  # noqa: BLE001 — sin ledger no hay regla (abstención)
        return None, []
    sums: Dict[str, float] = {}
    for r in rows:
        if r.get("status") != "closed" or r.get("open_fill_price") is None:
            continue
        d = str(r.get("exit_date") or "")[:10]
        if not d:
            continue
        sums[d] = sums.get(d, 0.0) + float(r.get("pnl_r") or 0.0)
    today_pnl = sums.pop(today_iso, None)
    history = [sums[d] for d in sorted(sums)]
    return today_pnl, history


def fill_rate_counts_today(telemetry, today_iso: str) -> Tuple[int, int]:
    """(n_total, n_filled) de las órdenes del día en execution_telemetry (A5).

    Filtra por `run_ref` (el día de trading de la fase que envió la orden),
    no por `ts` (hora de escritura) — determinista y semánticamente "del día".
    """
    if telemetry is None:
        return 0, 0
    try:
        rows = telemetry.fetch()
    except Exception:  # noqa: BLE001 — sin telemetría no hay regla (abstención)
        return 0, 0
    todays = [r for r in rows if str(r.get("run_ref") or "") == today_iso]
    n_total = len(todays)
    n_filled = sum(1 for r in todays
                   if r.get("status") == "submitted" and r.get("fill_price") is not None)
    return n_total, n_filled


# --------------------------------------------------------------------------
# Estado (pico de equity) + STOP_FILE + notificación
# --------------------------------------------------------------------------

def _load_peak(state_path: str) -> Optional[float]:
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            return float(json.load(fh).get("peak_equity"))
    except Exception:  # noqa: BLE001 — sin estado = primera vez
        return None


def update_peak_equity(equity: Optional[float],
                       state_path: str = STATE_FILE_PATH) -> Optional[float]:
    """Ratchet del pico de equity — solo sube. Devuelve el pico vigente."""
    if equity is None or float(equity) <= 0:
        return _load_peak(state_path)
    peak = _load_peak(state_path)
    if peak is None or float(equity) > peak:
        peak = float(equity)
        d = os.path.dirname(state_path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"peak_equity": peak,
                       "updated": datetime.now().isoformat(timespec="seconds")},
                      fh, indent=2)
        os.replace(tmp, state_path)
    return peak


def read_stop(stop_path: str = STOP_FILE_PATH) -> Optional[Dict[str, Any]]:
    """Contenido del STOP_FILE o None si no está activo. Presencia = pausa,
    aunque el contenido no parsee (fail-closed, nunca fail-open)."""
    if not os.path.exists(stop_path):
        return None
    try:
        with open(stop_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {"summary": "STOP_FILE presente (contenido no-JSON)", "raw": True}


def is_stopped(stop_path: str = STOP_FILE_PATH) -> bool:
    return os.path.exists(stop_path)


def notify_macos(title: str, message: str) -> bool:
    """Notificación macOS vía osascript — piso sin Telegram, best-effort."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message[:200]}" with title "{title}"'],
            check=False, timeout=5)
        return True
    except Exception:  # noqa: BLE001 — notificar jamás rompe el pipeline
        return False


def enforce_stop(fired_rules: List[Dict[str, Any]],
                 stop_path: str = STOP_FILE_PATH,
                 notify: bool = True,
                 now: Optional[str] = None) -> Dict[str, Any]:
    """Escribe el STOP_FILE con evidencia + notifica (una vez por evento).

    El STOP activo bloquea las ENTRADAS futuras; EXIT/reconcile jamás. El
    rearme es manual (ver REARME_HINT dentro del propio archivo).
    """
    fired = list(fired_rules or [])
    payload = {
        "fired_at": now or datetime.now().isoformat(timespec="seconds"),
        "summary": "; ".join(r.get("summary", r.get("rule", "?")) for r in fired),
        "fired_rules": fired,
        "rearme": REARME_HINT,
        "gate": ("Días bajo STOP no cuentan como limpios "
                 "(interrupción, por definición del gate)."),
    }
    d = os.path.dirname(stop_path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = stop_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, stop_path)
    if notify:
        notify_macos("fortress_core kill-switch", f"STOP: {payload['summary']}")
    return payload
