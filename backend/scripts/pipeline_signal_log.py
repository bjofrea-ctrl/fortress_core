"""
Logger best-effort de senales/ordenes del pipeline diario (Track B — paso 4b).

Registra en backend/data/pipeline_signal_log.jsonl lo que el pipeline DECIDE y
EJECUTA cada corrida, en un esquema fijo que la futura reconciliacion
(paso 4c, en 2-4 semanas, cuando haya 60-90 dias de paper trading) va a
consumir para comparar contra el backtest_engine sobre el mismo periodo.

Diseno: PRE_REGISTRO_RECONCILIACION_PIPELINE_BACKTEST.md (metodo congelado).
FUDE (Fuera de Alcance Definido): este modulo NO compara, NO alerta, NO toca
signal_engine.py ni la logica de decision. Solo registra lo que ya se decidio
y ejecuto. La comparacion real es paso 4c.

Formato: JSONL (una linea JSON por evento). Append-only, atomico por linea.
Best-effort: cualquier excepcion en el logging se traguea — un fallo de
logging JAMAS bloquea una orden real (contrato con pipeline_daily_signal.py).
"""
import datetime as dt
import json
import os
import threading
from typing import Any, Dict, List, Optional

LOG_DIR = os.path.join("data")
LOG_PATH = os.path.join(LOG_DIR, "pipeline_signal_log.jsonl")
_LOCK = threading.Lock()

# Campos esquema (PRE_REGISTRO_RECONCILIACION_PIPELINE_BACKTEST.md §2).
# 'event' discrimina: 'decision' (senal emitida en decide) vs
# 'execution' (orden ejecutada en enter/exit).
REQUIRED_FIELDS = (
    "event", "phase", "symbol", "signal_id", "side",
    "entry_date", "qty", "price_ref", "score",
    "fill_price", "client_order_id", "pipeline_run_ts", "source",
)


def _now_ts() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _safe_append(record: Dict[str, Any]) -> None:
    """Append de una linea, swallows todo error (best-effort, nunca rompe el flujo)."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _LOCK:
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — best-effort por contrato
        pass


def log_decision(signals: List[Dict[str, Any]], decision_date: str,
                 month_key: str, frozen_echo: Dict[str, Any]) -> None:
    """Registra las senales DECIDIDAS en phase_decide (todas, override tambien)."""
    ts = _now_ts()
    for s in signals:
        rec = {
            "event": "decision",
            "phase": "decide",
            "symbol": s.get("symbol"),
            "signal_id": s.get("signal_id") or f"{s.get('symbol')}__{decision_date}",
            "side": "buy",
            "entry_date": decision_date,
            "qty": None,           # todavia no se sizea
            "price_ref": s.get("price_ref"),
            "score": s.get("score"),
            "fill_price": None,    # todavia no se ejecuta
            "client_order_id": None,
            "pipeline_run_ts": ts,
            "source": "pipeline_daily_signal.phase_decide",
            "checkpoint_override": bool(s.get("checkpoint_override")),
            "frozen_echo": frozen_echo,
            "month_key": month_key,
        }
        _safe_append(rec)


def log_execution(phase: str, results: List[Dict[str, Any]]) -> None:
    """Registra los resultados de execute_plans en enter/exit."""
    ts = _now_ts()
    for r in results:
        rec = {
            "event": "execution",
            "phase": phase,
            "symbol": r.get("symbol"),
            "signal_id": r.get("sid"),
            "side": r.get("action"),
            "entry_date": None,   # se infiere de signal_id (__YYYY-MM-DD)
            "qty": r.get("qty"),
            "price_ref": None,    # no disponible en results; reside en state
            "score": None,        # reside en decision file
            "fill_price": r.get("fill"),
            "client_order_id": r.get("client_order_id"),
            "pipeline_run_ts": ts,
            "source": f"pipeline_daily_signal.phase_{phase}",
            "checkpoint_override": bool(r.get("checkpoint_override")),
            "status": r.get("status"),
            "skip_reason": r.get("skip_reason"),
            "error": r.get("error"),
        }
        _safe_append(rec)
