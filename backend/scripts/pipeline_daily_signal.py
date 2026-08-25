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
from app.core.indicators import calculate_all_indicators
from app.core.signal_engine import SignalEngine

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
               entry_date: dt.date, only_symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Planes de compra; salta signal_ids ya registrados (idempotencia).

    Los trades con checkpoint_override llevan sid prefijado chkpt__ para que
    jamás colisionen (ni se mezclen) con señales genuinas en el estado/ledger.
    """
    plans = []
    for o in sized:
        if only_symbols is not None and o["symbol"] not in only_symbols:
            continue
        override = bool(o.get("checkpoint_override"))
        sid = (CHECKPOINT_SID_PREFIX if override else "") + f"{o['symbol']}__{entry_date.isoformat()}"
        if sid in state["entries"] or (not override and f"{o['symbol']}__{entry_date.isoformat()}" in state["entries"]):
            plans.append({"action": "buy", "symbol": o["symbol"], "sid": sid,
                          "checkpoint_override": override,
                          "skip_reason": "ya_registrado_en_estado"})
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


def execute_plans(plans: List[Dict[str, Any]], state: Dict[str, Any],
                  dry_run: bool, phase: str, ref: dt.date,
                  client_factory=None) -> List[Dict[str, Any]]:
    """Ejecuta planes contra el cliente paper; muta y devuelve resultados por plan.

    En dry_run NUNCA construye cliente ni manda órdenes. En real, una orden
    rechazada/time-out se registra como error en la entrada y NO corta el resto.
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
        try:
            resp = client.submit_market_order(p["symbol"], p["qty"], side)
            fill = resp.get("filled_avg_price") if isinstance(resp, dict) else None
            res.update({"status": "submitted", "qty": p["qty"], "fill": fill, "client_order_id": coid})
        except Exception as exc:  # noqa: BLE001 — registrar y seguir (patrón repo)
            res.update({"status": "error", "error": str(exc)[:200]})
            if p["action"] == "buy":
                state["entries"][p["sid"]] = {
                    "symbol": p["symbol"], "status": "ERROR",
                    "error": str(exc)[:200],
                }
            results.append(res)
            continue
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
        else:
            e = state["entries"][p["sid"]]
            e.update({"status": "CLOSED", "exit_date": ref.isoformat(),
                      "sell_fill": fill, "sell_client_order_id": coid})
            if e.get("checkpoint_override"):
                e["exit_note"] = OVERRIDE_NOTE
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


def _equity_budget(lines: List[str]):
    """Presupuesto: equity real vía extensión de Cline si existe; si no, fallback."""
    try:
        from app.core.execution_costs import AlpacaPaperClient
        client = AlpacaPaperClient()
        if hasattr(client, "get_account"):
            acct = client.get_account()
            eq = float(acct.get("equity"))
            lines.append(f"Equity fuente: get_account() = {eq}")
            return eq, "account", client
        client.close()
    except Exception as exc:  # noqa: BLE001
        lines.append(f"[info] cuenta no disponible ({str(exc)[:80]}) -> fallback")
    lines.append(f"Equity fuente: FALLBACK constante {PAPER_CAPITAL_BUDGET} "
                 "(extension get_account de Cline aun no existe)")
    return PAPER_CAPITAL_BUDGET, "fallback", None


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
    budget, src, _client = _equity_budget(lines)
    sized = sizing(signals, budget)
    lines.append(f"Senales: {len(signals)} | presupuesto {budget} ({src}) | tamanos: "
                 + ", ".join(f"{o['symbol']}x{o['qty']}" for o in sized))
    state = load_state()
    plans = plan_enter(state, mk, sized, today, only_symbols=only_symbols)
    results = execute_plans(plans, state, dry_run, "enter", today,
                            client_factory=(None if dry_run else _make_client_factory()))
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
        return AlpacaPaperClient()
    return factory


def phase_exit(dry_run: bool, only_symbols: Optional[List[str]]) -> int:
    lines = ["Pipeline EXIT — venta mecanica de posiciones OPEN del pipeline", "=" * 62]
    state = load_state()
    open_n = sum(1 for e in state["entries"].values() if e.get("status") == "OPEN")
    lines.append(f"Posiciones OPEN en estado propio: {open_n}")
    plans = plan_exit(state, only_symbols=only_symbols)
    results = execute_plans(plans, state, dry_run, "exit", dt.date.today(),
                            client_factory=(None if dry_run else _make_client_factory()))
    if not dry_run:
        save_state(state)
    lines += ["", f"Resultados ({'DRY-RUN' if dry_run else 'REAL'}):"]
    for r in results:
        lines.append(f"  {r['action']:4s} {r['symbol']:5s} {r.get('status')}"
                     + (f" qty={r['qty']} fill={r.get('fill')}" if "qty" in r else "")
                     + (f" [{r.get('reason')}]" if r.get("reason") else ""))
    if open_n == 0:
        lines.append("(sin posiciones: fase no-op — normal fuera de ciclo mensual)")
    payload = {"phase": "exit", "dry_run": dry_run, "open_before": open_n, "results": results}
    _artifact(lines, payload, "exit")
    return 0


def phase_health() -> int:
    lines = ["Pipeline HEALTH", "=" * 40]
    stale = _cache_stale_days()
    ok = stale <= STALENESS_MAX_DAYS
    lines.append(f"Cache: ultimo habil hace {stale} dias -> {'OK' if ok else 'ESTANCADO'}")
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
