"""
Pipeline diario señal→orden papel→ledger (Frente 2 — PLAN_MAESTRO_FASE_PRODUCCION.md).

Diseño: PLAN_PIPELINE_DIARIO_FRENTE2.md (aprobado por coordinación 2026-08-25).
Definición de señal CONGELADA = exactamente la de scripts/validacion_oos_fresca_mom_rsi.py:
pesos leídos del motor EN RUNTIME (SignalEngine.factor_weights[0]), umbral 0.60,
gates duros (close>ema50>ema200, adx>=20, 40<rsi<75, volume_ratio>=1.0).
NO se usa generate_signal() completa (agregaría regime-gate/MIN_RR/stops que la
definición congelada excluye explícitamente). Nada se re-optimiza jamás.

Fases (cadencia MENSUAL fiel al backtest; cron diario, actúa solo en 3 momentos):
  decide  ~22:10 local tras data_updater, último hábil del mes:
          calcula señal desde el close fresco -> decision file atómico.
  enter   ~09:35 ET primer hábil del mes: lee decision file, compra equal-weight,
          registra entradas (staging propio; migrará al ledger de Cline).
  exit    ~15:40 ET último hábil del mes: vende todas las posiciones OPEN del estado.
  health  cualquier día: chequeo de frescura de cache y estado (sin órdenes).
  auto    elige fase por calendario (conveniencia; el cron pasa fase explícita).

Idempotencia: cada orden planeada lleva client_order_id determinista
(fc-{phase}-{yyyymm}-{symbol}); hoy el cliente de Alpaca aún no acepta ese
parámetro (extensión de Cline pendiente, contrato en diseño §5) así que la
deduplicación real es el ESTADO: un signal_id ya registrado nunca se re-envía.

Ledger: signal_ledger.py exige salida NOT NULL y solo escribe retroactivo
(label_symbol); la integración de entradas en vivo ES tarea de Cline. Este
pipeline registra en SU estado propio (data/cache/pipeline_state.json) filas
completas compra/venta para migrar 1:1 cuando esa pieza exista. No se toca
signal_ledger.py desde acá (no pisar trabajo ajeno).

Checkpoint Semana 1 (PLAN_PIPELINE_DIARIO_FRENTE2.md §6): corrida MANUAL completa
verificando orden ejecutada + registro + re-run sin duplicados ANTES de instalar
cualquier plist. Sin eso verificado, nada automático.

Uso:
  cd backend && .venv/bin/python -m scripts.pipeline_daily_signal --phase auto
  ... --phase decide [--dry-run] | --phase enter [--dry-run] [--symbols AAPL,MSFT]
  ... --phase exit [--dry-run] | --phase health
Salida: data/cache/pipeline_run_<ts>.txt (+ .json) y estado en
data/cache/pipeline_state.json. Nunca conecta a broker real: paper only.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS as UNIVERSE
from app.config import settings

# A5 (PLAN_REMEDIO_BRECHAS_20260903): slippage implicito por orden — libro de
# costos propio. Import liviano (sqlite3 + typing), sin estado global.
from app.core.execution_telemetry import ExecutionTelemetry, compute_slippage  # noqa: E402
from app.core.indicators import calculate_all_indicators
from app.core.signal_engine import SignalEngine

# A3 (PLAN_REMEDIO_BRECHAS_20260903): kill-switch por divergencia — reglas
# pre-declaradas. Import sin estado global; los gatherers reciben los
# objetos por parámetro (testeable con fixtures).
from scripts.kill_switch import (  # noqa: E402
    REARME_HINT,
    daily_pnls_from_ledger,
    enforce_stop,
    evaluate_fill_rate,
    evaluate_health,
    evaluate_pre_order,
    fill_rate_counts_today,
    is_stopped,
    read_stop,
    update_peak_equity,
)

# Track B (paso 4b): logging best-effort de senales/ordenes para futura
# reconciliacion pipeline-backtest (paso 4c, en 2-4 semanas).
# FUDE: este import NO activa ninguna comparacion ni alerta — solo registra.
from scripts.pipeline_signal_log import log_decision, log_execution  # noqa: E402

CACHE_DIR = os.path.join("data", "cache")
STATE_PATH = os.path.join(CACHE_DIR, "pipeline_state.json")
DECISION_PREFIX = os.path.join(CACHE_DIR, "pipeline_decision_")
ARTIFACT_DIR = CACHE_DIR
CALENDAR_SYMBOL = "SPY"
STALENESS_MAX_DAYS = 6          # fin de semana + feriado US + margen
PAPER_CAPITAL_BUDGET = 25000.0  # fallback si la lectura de cuenta (Cline) no existe

# ---- Definición CONGELADA (valores eco para auditoría; los pesos vivos vienen
# ---- del motor en runtime vía frozen_echo()). Fuente literal:
# ---- validacion_oos_fresca_mom_rsi.py:58-62 (que referencia signal_engine.py:216).
ENTRY_THRESHOLD = 0.60
RSI_SCORE_BAND = (45, 70)
RSI_GATE = (40, 75)
ADX_MIN = 20
VR_MIN = 1.0


# --------------------------------------------------------------------------
# Definición congelada
# --------------------------------------------------------------------------

def frozen_echo() -> Dict[str, Any]:
    """Valores vigentes LEÍDOS DEL MOTOR en runtime + constantes congeladas."""
    eng = SignalEngine(regime_classifier=None)
    w = eng.factor_weights[0]
    return {
        "w_mom_runtime": w["momentum"],
        "w_rsi_runtime": w["rsi"],
        "entry_threshold": ENTRY_THRESHOLD,
        "rsi_score_band": list(RSI_SCORE_BAND),
        "rsi_gate": list(RSI_GATE),
        "adx_min": ADX_MIN,
        "vr_min": VR_MIN,
        "cost_per_side": float(settings.COST_PER_SIDE),
        "slippage_referencia": 0.0005,
        "universe_n": len(UNIVERSE),
        "fuente": "validacion_oos_fresca_mom_rsi.py (congelada; pesos del motor en runtime)",
    }


def load_symbol(symbol: str):
    """Patrón EXACTO de validacion_oos_fresca_mom_rsi.load_symbol."""
    path = os.path.join(CACHE_DIR, symbol + ".parquet")
    if not os.path.exists(path):
        return None, None
    df = pd.read_parquet(path)
    df.columns = [str(c).lower() for c in df.columns]
    missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise RuntimeError(symbol + ": columnas faltantes " + str(missing))
    df = df.sort_index()
    ind = calculate_all_indicators(df.copy())
    if len(ind) == 0:
        return None, None
    return df, ind


def latest_signal(eng: SignalEngine, ind: pd.DataFrame) -> Optional[Dict[str, float]]:
    """Señal de HOY con la definición congelada sobre la última barra.

    Devuelve {'eligible':bool,'score':float,'close':float} o None si no hay filas.
    Usa compute_factor_frame (gates duros) + compute_score_series (score compuesto
    con pesos del motor, régimen 0) — camino verificado max|Δ|=0 vs la validación.
    """
    if len(ind) == 0:
        return None
    frame = eng.compute_factor_frame(ind)
    score = eng.compute_score_series(ind, regime_state=0)
    eligible = bool(frame["eligible"].iloc[-1])
    s = score.iloc[-1]
    return {
        "eligible": eligible,
        "score": float(s) if pd.notna(s) else 0.0,
        "close": float(frame["close"].iloc[-1]),
    }


CHECKPOINT_SID_PREFIX = "chkpt__"
OVERRIDE_NOTE = "OVERRIDE_MECANISMO — no es señal real"


def apply_checkpoint_injection(signals: List[Dict[str, Any]], inject_symbols: List[str],
                               price_lookup) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Inyecta símbolos SOLO para validar el mecanismo del tubo (Checkpoint S1).

    Marca cada uno con checkpoint_override=True; el par real/simulado NUNCA se
    mezcla: si el símbolo ya viene en una señal GENUINA del día, no se duplica ni
    se marca (el trade sería real, no de mecanismo). Devuelve (lista_final, notas).
    Aprobado por coordinación 2026-08-25 (equivalente operativo al M4: validar el
    tubo no es investigación ni consume Bonferroni).
    """
    out = [dict(s) for s in signals]
    notes: List[str] = []
    existing = {s["symbol"] for s in out}
    for sym in inject_symbols:
        if sym in existing:
            notes.append(f"{sym}: ya era señal GENUINA del dia — no se marca override")
            continue
        info = price_lookup(sym) or {}
        out.append({"symbol": sym,
                    "score": round(float(info.get("score") or 0.0), 6),
                    "price_ref": round(float(info.get("close") or 0.0), 4),
                    "checkpoint_override": True})
        notes.append(f"{sym}: INYECTADO para mecanismo (gates reales NO evaluados como filtro)")
    return out, notes


def ledger_row_payload(entry: Dict[str, Any], exit_reason: str = "",
                       pnl_r: Optional[float] = None) -> Dict[str, Any]:
    """Contrato EXACTO de la futura fila de signal_ledger (integra Cline).

    Condición (b) del gate 2026-08-25: un trade de mecanismo JAMÁS se mezcla con
    evidencia — marca triple: prefijo chkpt__ en signal_id, flag dentro de
    factors_json y prefijo en exit_reason.
    """
    override = bool(entry.get("checkpoint_override"))
    sid = entry.get("signal_id") or ""
    if override and not sid.startswith(CHECKPOINT_SID_PREFIX):
        sid = CHECKPOINT_SID_PREFIX + sid
    reason = (OVERRIDE_NOTE + " | " + exit_reason) if (override and exit_reason) else (
        OVERRIDE_NOTE if override else exit_reason)
    factors = {"checkpoint_override": True} if override else {}
    return {
        "signal_id": sid,
        "symbol": entry.get("symbol"),
        "entry_date": entry.get("entry_date"),
        "exit_date": entry.get("exit_date"),
        "exit_reason": reason,
        "pnl_r": pnl_r,
        "factors_json": json.dumps(factors, ensure_ascii=False),
        "regime_state": 0,
    }


def compute_signals(verbose_lines: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Aplica la definición congelada al universo completo (datos del cache)."""
    eng = SignalEngine(regime_classifier=None)
    signals: List[Dict[str, Any]] = []
    n_loaded = n_failed = 0
    for sym in UNIVERSE:
        try:
            _, ind = load_symbol(sym)
        except RuntimeError as exc:
            verbose_lines.append(f"[warn] {sym}: {exc}")
            n_failed += 1
            continue
        if ind is None:
            n_failed += 1
            continue
        n_loaded += 1
        sig = latest_signal(eng, ind)
        if sig is None:
            continue
        if sig["eligible"] and sig["score"] >= ENTRY_THRESHOLD:
            signals.append({"symbol": sym, "score": round(sig["score"], 6),
                            "price_ref": round(sig["close"], 4)})
    stats = {"n_loaded": n_loaded, "n_failed": n_failed, "n_signals": len(signals)}
    return sorted(signals, key=lambda x: -x["score"]), stats


# --------------------------------------------------------------------------
# Calendario (índice del parquet SPY = calendario US real con feriados)
# --------------------------------------------------------------------------

def trading_days() -> pd.DatetimeIndex:
    path = os.path.join(CACHE_DIR, CALENDAR_SYMBOL + ".parquet")
    if not os.path.exists(path):
        raise RuntimeError(f"calendario no disponible: falta {CALENDAR_SYMBOL}.parquet")
    idx = pd.read_parquet(path).index
    return pd.DatetimeIndex(pd.to_datetime(idx)).normalize().unique().sort_values()


def month_bounds(days: pd.DatetimeIndex, ref: dt.date) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    """Primer y último día hábil del mes de ref según el calendario del cache."""
    ts = pd.Timestamp(ref)
    mask = (days.year == ts.year) & (days.month == ts.month)
    sub = days[mask]
    if len(sub) == 0:
        return None, None
    return sub[0].date(), sub[-1].date()


def detect_auto_phase(ref: Optional[dt.date] = None) -> str:
    ref = ref or dt.date.today()
    days = trading_days()
    first, last = month_bounds(days, ref)
    if last is not None and ref == last:
        return "exit" if ref.weekday() != 6 else "health"  # DECIDE corre aparte 22:10
    if first is not None and ref == first:
        return "enter"
    return "health"


# --------------------------------------------------------------------------
# Estado propio del pipeline (staging hasta que exista el ledger de Cline)
# --------------------------------------------------------------------------

def new_state() -> Dict[str, Any]:
    return {"schema": 1, "entries": {}, "months": {}}


def load_state(path: str = STATE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return new_state()
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state: Dict[str, Any], path: str = STATE_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def client_order_id(phase: str, ref: dt.date, symbol: str) -> str:
    return f"fc-{phase}-{ref.strftime('%Y%m')}-{symbol}"


# --------------------------------------------------------------------------
# Sizing y planes (funciones puras, testeable sin red)
# --------------------------------------------------------------------------

def sizing(signals: List[Dict[str, Any]], budget: float) -> List[Dict[str, Any]]:
    """Equal-weight: qty = floor((budget / n) / price_ref). Qty>=1 requerido."""
    n = max(len(signals), 1)
    per = budget / n
    out = []
    for s in signals:
        qty = int(math.floor(per / s["price_ref"])) if s["price_ref"] > 0 else 0
        out.append({**s, "qty": qty, "notional_ref": round(qty * s["price_ref"], 2)})
    return [o for o in out if o["qty"] >= 1]


def plan_enter(state: Dict[str, Any], month: str, sized: List[Dict[str, Any]],
               entry_date: dt.date, only_symbols: Optional[List[str]] = None,
               skip_sids: Optional[set] = None,
               held_symbols: Optional[set] = None) -> List[Dict[str, Any]]:
    """Planes de compra; salta signal_ids ya registrados (idempotencia).

    Capas anti-duplicado (en orden): estado propio -> ledger real (skip_sids)
    -> posición ya tenida en el broker (held_symbols). Los trades con
    checkpoint_override llevan sid prefijado chkpt__ para que jamás colisionen
    ni se mezclen con señales genuinas en el estado/ledger.
    """
    plans = []
    for o in sized:
        if only_symbols is not None and o["symbol"] not in only_symbols:
            continue
        override = bool(o.get("checkpoint_override"))
        sid = (CHECKPOINT_SID_PREFIX if override else "") + f"{o['symbol']}__{entry_date.isoformat()}"
        plain_sid = f"{o['symbol']}__{entry_date.isoformat()}"
        if sid in state["entries"] or (not override and plain_sid in state["entries"]):
            plans.append({"action": "buy", "symbol": o["symbol"], "sid": sid,
                          "checkpoint_override": override,
                          "skip_reason": "ya_registrado_en_estado"})
            continue
        if skip_sids and (sid in skip_sids or plain_sid in skip_sids):
            plans.append({"action": "buy", "symbol": o["symbol"], "sid": sid,
                          "checkpoint_override": override,
                          "skip_reason": "ya_abierta_en_ledger"})
            continue
        if held_symbols and o["symbol"] in held_symbols:
            plans.append({"action": "buy", "symbol": o["symbol"], "sid": sid,
                          "checkpoint_override": override,
                          "skip_reason": "posicion_existente_en_broker"})
            continue
        plans.append({"action": "buy", "symbol": o["symbol"], "sid": sid,
                      "qty": o["qty"], "price_ref": o["price_ref"],
                      "checkpoint_override": override})
    return plans


def plan_exit(state: Dict[str, Any], only_symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Vende TODA posición OPEN registrada por este pipeline (salida mecánica)."""
    plans = []
    for sid, e in sorted(state["entries"].items()):
        if e.get("status") != "OPEN":
            continue
        if only_symbols is not None and e["symbol"] not in only_symbols:
            continue
        plans.append({"action": "sell", "symbol": e["symbol"], "sid": sid, "qty": e["qty"]})
    return plans


def _net_return_r(buy_fill: Optional[float], sell_fill: Optional[float],
                  price_ref: Optional[float] = None) -> float:
    """Retorno neto de costs como pnl_r (denominador r=1: la def congelada no
    tiene stops — limitación §7 declarada, misma del backtest mensual)."""
    c = float(settings.COST_PER_SIDE) + 0.0005
    buy = float(buy_fill if buy_fill else (price_ref or 0.0))
    sell = float(sell_fill or 0.0)
    if buy <= 0 or sell <= 0:
        return 0.0
    return ((sell * (1 - c)) / (buy * (1 + c))) - 1.0


def execute_plans(plans: List[Dict[str, Any]], state: Dict[str, Any],
                  dry_run: bool, phase: str, ref: dt.date,
                  client_factory=None, ledger=None,
                  telemetry=None) -> List[Dict[str, Any]]:
    """Ejecuta planes contra el cliente paper; muta y devuelve resultados por plan.

    En dry_run NUNCA construye cliente ni manda órdenes. En real, una orden
    rechazada/time-out se registra como error en la entrada y NO corta el resto.
    Si se pasa `ledger` (SignalLedger real), compra abre fila (open_order) y
    venta la cierra (close_order) — fuente de verdad desde merge 838934b.
    Telemetría A5: si se pasa `telemetry` (ExecutionTelemetry), cada orden
    enviada (submitted o error) queda en la tabla execution_telemetry con
    decision_price/fill_price/slippage_implicit. En dry_run no registra (no
    hay orden real que medir).
    """
    results = []
    client = None
    for p in plans:
        res = {k: p[k] for k in ("action", "symbol", "sid")}
        if p.get("checkpoint_override"):
            res["checkpoint_override"] = True
        if "skip_reason" in p:
            res.update({"status": "skipped", "reason": p["skip_reason"]})
            results.append(res)
            continue
        if dry_run:
            res.update({"status": "dry_run_plan", "qty": p.get("qty")})
            results.append(res)
            continue
        if client is None:
            if client_factory is None:
                raise RuntimeError("modo real requiere client_factory (AlpacaPaperClient)")
            client = client_factory()
        side = "buy" if p["action"] == "buy" else "sell"
        coid = client_order_id(phase, ref, p["symbol"])
        # A5: precio de decisión ANTES del submit (para buy, el price_ref de la
        # señal; para sell, el último trade del símbolo — la referencia contra
        # la que la salida mecánica decide vender).
        decision_price: Optional[float] = None
        if side == "buy":
            decision_price = p.get("price_ref")
        else:
            try:
                decision_price = client.last_trade_price(p["symbol"])
            except Exception:  # noqa: BLE001 — la venta no depende del precio
                decision_price = None
        try:
            resp = client.submit_market_order(p["symbol"], p["qty"], side)
            fill = resp.get("filled_avg_price") if isinstance(resp, dict) else None
            res.update({"status": "submitted", "qty": p["qty"], "fill": fill, "client_order_id": coid})
        except Exception as exc:  # noqa: BLE001 — registrar y seguir (patrón repo)
            res.update({"status": "error", "error": str(exc)[:200]})
            if telemetry is not None:
                telemetry.record(phase=phase, run_ref=ref.isoformat(),
                                 symbol=p["symbol"], side=side, qty=p["qty"],
                                 decision_price=decision_price, fill_price=None,
                                 checkpoint_override=bool(p.get("checkpoint_override")),
                                 client_order_id=coid, status="error",
                                 error=str(exc)[:200])
            if p["action"] == "buy":
                state["entries"][p["sid"]] = {
                    "symbol": p["symbol"], "status": "ERROR",
                    "error": str(exc)[:200],
                }
            results.append(res)
            continue
        # A5: fila de telemetría por orden enviada (fill real).
        if telemetry is not None:
            telemetry.record(phase=phase, run_ref=ref.isoformat(),
                             symbol=p["symbol"], side=side, qty=p["qty"],
                             decision_price=decision_price, fill_price=fill,
                             checkpoint_override=bool(p.get("checkpoint_override")),
                             client_order_id=coid, status="submitted")
            res["decision_price"] = decision_price
            res["slippage_implicit"] = compute_slippage(decision_price, fill)
        if side == "buy":
            prev = state["entries"].get(p["sid"])
            state["entries"][p["sid"]] = {
                "symbol": p["symbol"], "status": "OPEN",
                "checkpoint_override": bool(p.get("checkpoint_override")),
                "entry_date": ref.isoformat(),
                "qty": p["qty"], "price_ref": p.get("price_ref"),
                "buy_fill": fill, "buy_client_order_id": coid,
                "prev_error": (prev or {}).get("error"),
            }
            if ledger is not None:
                ledger.open_order(
                    p["sid"], p["symbol"], ref.isoformat(), p["qty"],
                    float(fill) if fill is not None else float(p.get("price_ref") or 0.0),
                    factors=({"checkpoint_override": True} if p.get("checkpoint_override") else None),
                )
        else:
            e = state["entries"].get(p["sid"])
            override = bool((e or p).get("checkpoint_override")) or p["sid"].startswith(CHECKPOINT_SID_PREFIX)
            if e is not None:
                e.update({"status": "CLOSED", "exit_date": ref.isoformat(),
                          "sell_fill": fill, "sell_client_order_id": coid})
                if override:
                    e["exit_note"] = OVERRIDE_NOTE
            if ledger is not None:
                reason = f"{OVERRIDE_NOTE} | MONTH_END" if override else "MONTH_END"
                pnl_r = _net_return_r((e or {}).get("buy_fill"), fill,
                                      (e or {}).get("price_ref"))
                ledger.close_order(p["sid"], ref.isoformat(), reason,
                                   round(pnl_r, 6), fill)
        results.append(res)
    return results


# --------------------------------------------------------------------------
# Fases
# --------------------------------------------------------------------------

def _artifact(lines: List[str], payload: Dict[str, Any], tag: str) -> str:
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join(ARTIFACT_DIR, f"pipeline_run_{tag}_{ts}.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(txt_path.replace(".txt", ".json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    print("\n".join(lines))
    print(f"\nOut: {txt_path}\nOut: {txt_path.replace('.txt', '.json')}")
    print(f"ARTIFACT:{txt_path}")
    return txt_path


def _cache_stale_days() -> int:
    days = trading_days()
    return (pd.Timestamp(dt.date.today()) - days[-1]).days


def _cache_stale_ruedas() -> Optional[int]:
    """Ruedas (días hábiles Lun-Vie) desde la última barra del cache.

    Para la regla (iv) del kill-switch (A3): staleness > 2 ruedas = updater
    muerto. None si el calendario no está disponible (abstención).
    """
    try:
        days = trading_days()
    except Exception:  # noqa: BLE001 — sin parquet SPY no hay calendario
        return None
    last = days[-1].date() if len(days) else None
    if last is None:
        return None
    # días hábiles (Lun-Vie) estrictamente posteriores a la última barra
    n = 0
    d = last
    today = dt.date.today()
    while d < today:
        d = d + dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def phase_decide(dry_run: bool, inject_symbols: Optional[List[str]] = None) -> int:
    lines = ["Pipeline DECIDE — señal con definición CONGELADA (sin re-optimizar)",
             "=" * 74]
    stale = _cache_stale_days()
    lines.append(f"Frescura cache: ultimo habil hace {stale} dias (max {STALENESS_MAX_DAYS})")
    if stale > STALENESS_MAX_DAYS:
        lines.append("[abort] cache estancado: NO se decide con datos viejos "
                     "(precedente updater caido 2026-08-15/22). Revisar data_updater.")
        _artifact(lines, {"phase": "decide", "aborted": "cache_stale", "stale_days": stale}, "decide")
        return 1
    signals, stats = compute_signals(lines)
    notes: List[str] = []
    if inject_symbols:
        eng = SignalEngine(regime_classifier=None)

        def price_lookup(sym):
            _, ind = load_symbol(sym)
            return latest_signal(eng, ind) if ind is not None else None

        signals, notes = apply_checkpoint_injection(signals, inject_symbols, price_lookup)
        signals.sort(key=lambda x: -x["score"])
    echo = frozen_echo()
    if inject_symbols:
        # Condición (a) del gate 2026-08-25: marca visible DENTRO del frozen_echo.
        echo["override_mecanismo"] = (
            "OVERRIDE_MECANISMO — no es señal real. Corrida de checkpoint para "
            "validar el tubo (orden+registro); NO usar como historial de señal.")
    today = dt.date.today()
    mk = today.strftime("%Y%m")
    # Track B (paso 4b): log best-effort de senales decididas (FUDE: no decide nada).
    log_decision(signals, today.isoformat(), mk, echo)
    payload = {"phase": "decide", "decision_date": today.isoformat(),
               "month_key": mk, "frozen_echo": echo, "stats": stats, "signals": signals,
               "checkpoint_notes": notes, "dry_run": dry_run}
    if inject_symbols:
        lines += ["", "!! OVERRIDE_MECANISMO — no es senal real !!",
                  "!! Simbolos inyectados SOLO para validar el tubo (Checkpoint S1): "
                  + ", ".join(inject_symbols), ""]
    lines += ["", f"Universo cargado: {stats['n_loaded']}/{len(UNIVERSE)} | senales: {stats['n_signals']}"]
    for s in signals:
        tag = " [OVERRIDE_MECANISMO]" if s.get("checkpoint_override") else ""
        lines.append(f"  BUY {s['symbol']:5s} score={s['score']:.4f} ref={s['price_ref']}{tag}")
    for n in notes:
        lines.append(f"  nota: {n}")
    lines.append("")
    lines.append("Frozen echo: " + json.dumps(echo, ensure_ascii=False))
    if not dry_run:
        path = f"{DECISION_PREFIX}{mk}.json"
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        lines.append(f"Decision file: {path}")
    else:
        lines.append("DRY-RUN: decision file NO escrito.")
    _artifact(lines, payload, "decide")
    return 0


def plan_exit_from_ledger(open_rows: List[Dict[str, Any]],
                          only_symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Planes de venta desde el LEDGER REAL (fuente de verdad, robusto a pérdida
    del estado propio). Marca override si el sid trae prefijo chkpt__."""
    plans = []
    for r in open_rows:
        sym = r.get("symbol")
        if only_symbols is not None and sym not in only_symbols:
            continue
        plans.append({"action": "sell", "symbol": sym,
                      "sid": r.get("signal_id"),
                      "qty": int(r.get("qty") or 0),
                      "checkpoint_override": str(r.get("signal_id", "")).startswith(CHECKPOINT_SID_PREFIX)})
    return [p for p in plans if p["qty"] >= 1]


def _open_client_and_budget(lines: List[str], dry_run: bool):
    """Un solo cliente para todo el run real: equity + posiciones + órdenes.

    Devuelve (client|None, budget, source, held_symbols:set). En dry_run no
    construye nada y devuelve fallback informativo.
    """
    if dry_run:
        lines.append(f"Equity fuente: FALLBACK (dry-run) {PAPER_CAPITAL_BUDGET}")
        return None, PAPER_CAPITAL_BUDGET, "dry_run_fallback", set()
    try:
        from app.core.execution_costs import AlpacaPaperClient
        # Fix: AlpacaPaperClient lee os.environ, pero pydantic-settings
        # no inyecta allí. Pasar keys de Settings al constructor directamente.
        client = AlpacaPaperClient(
            api_key=settings.ALPACA_PAPER_API_KEY,
            secret_key=settings.ALPACA_PAPER_SECRET_KEY,
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[info] cliente no construible ({str(exc)[:80]}) -> fallback")
        return None, PAPER_CAPITAL_BUDGET, "fallback", set()
    budget, src = PAPER_CAPITAL_BUDGET, "fallback_constante"
    held: set = set()
    try:
        acct = client.get_account()
        budget = float(acct.get("equity"))
        src = "get_account"
        lines.append(f"Equity fuente: get_account() = {budget}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[info] get_account fallo ({str(exc)[:60]}) -> {src}={budget}")
    try:
        held = {p["symbol"] for p in client.get_positions()}
        lines.append(f"Posiciones broker: {sorted(held) if held else 'ninguna'}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[info] get_positions fallo ({str(exc)[:60]})")
    return client, budget, src, held


def phase_enter(dry_run: bool, only_symbols: Optional[List[str]]) -> int:
    lines = ["Pipeline ENTER — compras equal-weight del decision file", "=" * 60]
    today = dt.date.today()
    mk = today.strftime("%Y%m")
    dpath = f"{DECISION_PREFIX}{mk}.json"
    if not os.path.exists(dpath):
        lines.append(f"[abort] sin decision file para {mk}: correr --phase decide primero.")
        _artifact(lines, {"phase": "enter", "aborted": "no_decision_file"}, "enter")
        return 1
    with open(dpath, "r", encoding="utf-8") as fh:
        dec = json.load(fh)
    signals = [s for s in dec["signals"]
               if only_symbols is None or s["symbol"] in only_symbols]
    # A3: STOP activo -> aborta entradas nuevas. EXIT y reconcile (fase exit)
    # NUNCA se bloquean — el STOP solo pausa comprometer dinero NUEVO.
    if is_stopped():
        stop = read_stop() or {}
        lines.append(f"[stop] KILL-SWITCH ACTIVO ({stop.get('fired_at', '?')}): "
                     "entradas nuevas en pausa. " + (stop.get('rearme', '') or ''))
        lines.append(f"[stop] motivo: {stop.get('summary', 'ver data/STOP_FILE')}")
        _artifact(lines, {"phase": "enter", "aborted": "kill_switch_stop",
                         "stop": stop}, "enter")
        return 1
    client, budget, src, held = _open_client_and_budget(lines, dry_run)
    # A3: reglas pre-orden (drawdown con equity real, pnl diario, staleness).
    # Solo en corrida real (dry-run no mide nada del paper). Un disparo
    # aquí frena ESTA fase antes de enviar la primera orden.
    if not dry_run:
        equity = None
        try:
            acct = client.get_account() if client is not None else None
            equity = float(acct.get("equity")) if isinstance(acct, dict) else None
        except Exception as exc:  # noqa: BLE001 — sin equity la regla se abstiene
            lines.append(f"[info] equity no legible para kill-switch ({str(exc)[:60]})")
        peak = update_peak_equity(equity)
        try:
            from app.core.signal_ledger import SignalLedger
            _led = SignalLedger()
            today_pnl, pnl_history = daily_pnls_from_ledger(_led, today.isoformat())
        except Exception as exc:  # noqa: BLE001 — sin ledger la regla (ii) se abstiene
            lines.append(f"[info] ledger no legible para kill-switch ({str(exc)[:60]})")
            today_pnl, pnl_history = None, []
        v = evaluate_pre_order(equity, peak, today_pnl, pnl_history,
                               _cache_stale_ruedas())
        for r in v["evaluated"]:
            tag = " STOP" if r["fired"] else (" (abstencion)" if r.get("abstained") else "")
            lines.append(f"[kill-switch] {r['summary']}{tag}")
        if v["stopped"]:
            enforce_stop(v["fired"])
            lines.append("[stop] KILL-SWITCH DISPARADO pre-orden: "
                         "NO se envían órdenes hoy. " + REARME_HINT)
            _artifact(lines, {"phase": "enter", "aborted": "kill_switch_pre_order",
                             "verdict": v}, "enter")
            return 1
    sized = sizing(signals, budget)
    lines.append(f"Senales: {len(signals)} | presupuesto {budget} ({src}) | tamanos: "
                 + ", ".join(f"{o['symbol']}x{o['qty']}" for o in sized))
    state = load_state()
    ledger = None
    skip_sids: set = set()
    telemetry = None
    if not dry_run:
        try:
            from app.core.signal_ledger import SignalLedger
            ledger = SignalLedger()
            skip_sids = {r["signal_id"] for r in ledger.open_orders()}
            lines.append(f"Open orders en ledger real: {len(skip_sids)}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"[warn] ledger no disponible ({str(exc)[:60]}) -> dedup solo estado propio")
        try:
            telemetry = ExecutionTelemetry()
        except Exception as exc:  # noqa: BLE001
            lines.append(f"[warn] telemetria no disponible ({str(exc)[:60]}) -> ordenes sin registro A5")
    plans = plan_enter(state, mk, sized, today, only_symbols=only_symbols,
                       skip_sids=skip_sids, held_symbols=held)
    results = execute_plans(plans, state, dry_run, "enter", today,
                            client_factory=(None if dry_run else (lambda: client)),
                            ledger=ledger, telemetry=telemetry)
    # Track B (paso 4b): log best-effort de ejecucion en enter (FUDE: no ejecuta nada).
    log_execution("enter", results)
    # A3: regla (iii) post-órdenes — fill rate del día (telemetría acumulada,
    # incluye corridas previas de hoy). Nunca deshace lo ejecutado; protege
    # las entradas FUTURAS.
    if not dry_run and telemetry is not None:
        n_total, n_filled = fill_rate_counts_today(telemetry, today.isoformat())
        v = evaluate_fill_rate(n_total, n_filled)
        r = v["evaluated"][0]
        tag = " STOP" if r["fired"] else (" (abstencion)" if r.get("abstained") else "")
        lines.append(f"[kill-switch] {r['summary']}{tag}")
        if v["stopped"]:
            enforce_stop(v["fired"])
            lines.append("[stop] KILL-SWITCH DISPARADO (fill rate): "
                         "entradas nuevas en pausa. " + REARME_HINT)
    state.setdefault("months", {}).setdefault(mk, {})["enter"] = (
        "dry_run" if dry_run else ("done" if all(r.get("status") != "error" for r in results) else "partial"))
    if not dry_run:
        save_state(state)
    lines += ["", f"Resultados ({'DRY-RUN' if dry_run else 'REAL'}):"]
    for r in results:
        tag = " [OVERRIDE_MECANISMO]" if r.get("checkpoint_override") else ""
        lines.append(f"  {r['action']:4s} {r['symbol']:5s} {r.get('status')}{tag}"
                     + (f" qty={r['qty']} fill={r.get('fill')}" if "qty" in r and r.get("status") != "skipped" else "")
                     + (f" [{r.get('reason')}]" if r.get("reason") else "")
                     + (f" ERROR={r['error']}" if r.get("error") else ""))
    payload = {"phase": "enter", "dry_run": dry_run, "budget_source": src,
               "budget": budget, "results": results, "decision_file": dpath}
    _artifact(lines, payload, "enter")
    return 0


def _make_client_factory():
    def factory():
        from app.core.execution_costs import AlpacaPaperClient
        return AlpacaPaperClient(
            api_key=settings.ALPACA_PAPER_API_KEY,
            secret_key=settings.ALPACA_PAPER_SECRET_KEY,
        )
    return factory


def phase_exit(dry_run: bool, only_symbols: Optional[List[str]]) -> int:
    lines = ["Pipeline EXIT — venta mecanica de posiciones OPEN del pipeline", "=" * 62]
    state = load_state()
    open_n = sum(1 for e in state["entries"].values() if e.get("status") == "OPEN")
    ledger = None
    telemetry = None
    open_rows: List[Dict[str, Any]] = []
    if not dry_run:
        try:
            from app.core.signal_ledger import SignalLedger
            ledger = SignalLedger()
            open_rows = ledger.open_orders()
        except Exception as exc:  # noqa: BLE001
            lines.append(f"[warn] ledger no disponible ({str(exc)[:60]}) -> estado propio")
        try:
            telemetry = ExecutionTelemetry()
        except Exception as exc:  # noqa: BLE001
            lines.append(f"[warn] telemetria no disponible ({str(exc)[:60]}) -> ordenes sin registro A5")
    if open_rows:
        plans = plan_exit_from_ledger(open_rows, only_symbols)
        source = f"ledger real ({len(open_rows)} abiertas)"
    else:
        plans = plan_exit(state, only_symbols=only_symbols)
        source = "estado propio"
    lines.append(f"Fuente de verdad EXIT: {source} | OPEN estado={open_n}")
    results = execute_plans(plans, state, dry_run, "exit", dt.date.today(),
                            client_factory=(None if dry_run else _make_client_factory()),
                            ledger=ledger, telemetry=telemetry)
    # Track B (paso 4b): log best-effort de ejecucion en exit (FUDE: no ejecuta nada).
    log_execution("exit", results)
    # A3: regla (iii) post-órdenes también en EXIT — un fill rate roto al
    # VENDER es ejecución rota igual que al comprar (protege la próxima
    # entrada). El STOP jamás bloquea ESTA venta ya ejecutada.
    if not dry_run and telemetry is not None:
        n_total, n_filled = fill_rate_counts_today(telemetry, dt.date.today().isoformat())
        v = evaluate_fill_rate(n_total, n_filled)
        r = v["evaluated"][0]
        tag = " STOP" if r["fired"] else (" (abstencion)" if r.get("abstained") else "")
        lines.append(f"[kill-switch] {r['summary']}{tag}")
        if v["stopped"]:
            enforce_stop(v["fired"])
            lines.append("[stop] KILL-SWITCH DISPARADO (fill rate): "
                         "entradas nuevas en pausa. " + REARME_HINT)
    if not dry_run:
        save_state(state)
    lines += ["", f"Resultados ({'DRY-RUN' if dry_run else 'REAL'}):"]
    for r in results:
        tag = " [OVERRIDE_MECANISMO]" if r.get("checkpoint_override") else ""
        lines.append(f"  {r['action']:4s} {r['symbol']:5s} {r.get('status')}{tag}"
                     + (f" qty={r['qty']} fill={r.get('fill')}" if "qty" in r else "")
                     + (f" [{r.get('reason')}]" if r.get("reason") else ""))
    if not plans:
        lines.append("(sin posiciones: fase no-op — normal fuera de ciclo mensual)")
    payload = {"phase": "exit", "dry_run": dry_run, "open_before": open_n,
               "source": source, "results": results}
    _artifact(lines, payload, "exit")
    return 0


def phase_health() -> int:
    lines = ["Pipeline HEALTH", "=" * 40]
    stale = _cache_stale_days()
    ok = stale <= STALENESS_MAX_DAYS
    lines.append(f"Cache: ultimo habil hace {stale} dias -> {'OK' if ok else 'ESTANCADO'}")
    # A3: kill-switch — estado + reglas baratas (ii)+(iii)+(iv), sin cliente.
    if is_stopped():
        stop = read_stop() or {}
        lines.append(f"[stop] KILL-SWITCH ACTIVO desde {stop.get('fired_at', '?')} "
                     f"— {stop.get('summary', '')}")
    else:
        try:
            from app.core.signal_ledger import SignalLedger
            _led = SignalLedger()
            today_pnl, pnl_history = daily_pnls_from_ledger(_led, dt.date.today().isoformat())
        except Exception as exc:  # noqa: BLE001 — la regla (ii) se abstiene
            lines.append(f"[info] ledger no legible para kill-switch ({str(exc)[:60]})")
            today_pnl, pnl_history = None, []
        try:
            telemetry = ExecutionTelemetry()
            n_total, n_filled = fill_rate_counts_today(
                telemetry, dt.date.today().isoformat())
        except Exception as exc:  # noqa: BLE001 — la regla (iii) se abstiene
            lines.append(f"[info] telemetria no legible ({str(exc)[:60]})")
            n_total, n_filled = 0, 0
        v = evaluate_health(today_pnl, pnl_history, n_total, n_filled,
                            _cache_stale_ruedas())
        for r in v["evaluated"]:
            tag = " STOP" if r["fired"] else (" (abstencion)" if r.get("abstained") else "")
            lines.append(f"[kill-switch] {r['summary']}{tag}")
        if v["stopped"]:
            enforce_stop(v["fired"])
            lines.append("[stop] KILL-SWITCH DISPARADO: entradas nuevas en pausa. "
                         + REARME_HINT)
            ok = False
    state = load_state()
    open_n = sum(1 for e in state["entries"].values() if e.get("status") == "OPEN")
    closed_n = sum(1 for e in state["entries"].values() if e.get("status") == "CLOSED")
    err_n = sum(1 for e in state["entries"].values() if e.get("status") == "ERROR")
    lines.append(f"Estado: {open_n} OPEN / {closed_n} CLOSED / {err_n} ERROR | meses: {list(state.get('months', {}).keys())}")
    lines.append(f"Hoy: {dt.date.today()} | fase auto sugerida: {detect_auto_phase()}")
    payload = {"phase": "health", "stale_days": stale, "cache_ok": ok,
               "open": open_n, "closed": closed_n, "errors": err_n}
    _artifact(lines, payload, "health")
    return 0 if ok else 1


# --------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", choices=["auto", "decide", "enter", "exit", "health"],
                        default="auto")
    parser.add_argument("--dry-run", action="store_true",
                        help="calcula y reporta SIN enviar ordenes ni escribir estado")
    parser.add_argument("--symbols", default="",
                        help="filtro opcional 'AAPL,MSFT' (checkpoint controlado)")
    parser.add_argument("--checkpoint-inject", default="",
                        help="SOLO checkpoint S1: 'AAPL,MSFT' a inyectar para validar "
                             "el tubo. Marcado OVERRIDE_MECANISMO en artefacto y en la "
                             "fila futura de ledger (prefijo chkpt__). NUNCA es senal real.")
    args = parser.parse_args(argv)
    only = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    inject = [s.strip().upper() for s in args.checkpoint_inject.split(",") if s.strip()] or None
    phase = detect_auto_phase() if args.phase == "auto" else args.phase
    if phase == "decide":
        return phase_decide(args.dry_run, inject)
    if phase == "enter":
        return phase_enter(args.dry_run, only)
    if phase == "exit":
        return phase_exit(args.dry_run, only)
    return phase_health()


if __name__ == "__main__":
    sys.exit(main())
