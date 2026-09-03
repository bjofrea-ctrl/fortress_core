"""API routes — dashboard de apoyo a decisión institucional (advisor).

Solo LECTURA: no emite órdenes, no dispara LLM, no reprograma el motor.
Reutiliza `_compute_ticket`/`_load_context` de decision.py como la ÚNICA
fuente de verdad del ticket — la única lógica nueva acá es el MAPEO DE
ETIQUETAS de resultado proyectado (pre-registrado §29, no negociable) y el
Exit Thesis Monitor (tesis de entrada vs estado actual).

Contrato de honestidad (ONBOARDING #1/#4): ninguna etiqueta se presenta como
predicción; cada una lleva su n de evidencia. Win_prob alto no es certeza —
es la única selectividad medida y está documentada con su muestra chica.

Mapeo §29 (win_prob -> etiqueta), verificado contra
baseline_clean_20260811_150643_trades.parquet:
    >=0.70  -> GANANCIA_PROYECTADA_ALTA  (VPP 87.5%, n=8)
    0.65-0.70 -> GANANCIA_PROYECTADA     (VPP 73.7%, n=19)
    0.45-0.65 -> NEUTRO                  (sin selectividad medida)
    <0.45   -> RIESGOSA_SIN_APOYO        (cola baja, sin apoyo estadístico)

GET /api/advisor/universe — mesa consolidada del universo en UNA llamada.
GET /api/advisor/{symbol} — detalle: OHLCV EOD, overlays, exit plan, M2,
                            fundamentals (EDGAR o null honesto).
GET /api/advisor/theses   — Exit Thesis Monitor (tesis de entrada vs hoy).
GET /api/advisor/evidence — footer de confianza: ledger de trials.
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.routes.decision import (
    _STATE_RANK,
    DECISION_STATES_PATH,
    _compute_ticket,
    _exit_plan,
    _fit_calibrators,
    _fit_regime,
    _latest_prior_states,
    _load_market_data,
    _load_price_data,
    _load_states_history,
    _transition,
)
from app.api.routes.opportunities_universe import MARKET_TICKERS, SYMBOLS
from app.config import settings
from app.core import trial_registry
from app.core.edgar_fundamentals import get_edgar_fundamentals
from app.core.indicators import calculate_all_indicators, ema

router = APIRouter(prefix="/api/advisor", tags=["advisor"])

# Umbral §29 pre-registrado. Si cambia, cambiar SOLO acá + nueva sección doc.
LABEL_THRESHOLDS = [
    (0.70, "GANANCIA_PROYECTADA_ALTA"),
    (0.65, "GANANCIA_PROYECTADA"),
]
NEUTRO_FLOOR = 0.45

# Staleness: si el cache lleva >2 ruedas hábiles de atraso, avisar en UI.
MAX_STALE_BD = 2


def _projected_label(win_prob: Optional[float], calibrator_fitted: bool) -> Dict:
    """Mapeo §29 con la evidencia que la UI debe citar junto a la etiqueta.

    win_prob=None tiene dos causas distintas que NO deben confluir:
      - calibrador sin fittear -> SIN_CALIBRAR (no hay nada que presentar)
      - sin score (fuera de gate) -> SIN_SCORE
    La cola baja (<0.45) NO se presenta como "pérdida proyectada": no hay
    selectividad medida ahí (win_rate global 0.5874). Se presenta como
    RIESGOSA_SIN_APOYO explícito.
    """
    if win_prob is None:
        if not calibrator_fitted:
            return {"label": "SIN_CALIBRAR", "evidence": "calibrador no ajustado", "n": 0}
        return {"label": "SIN_SCORE", "evidence": "fuera de gate técnico (sin score)", "n": 0}

    base = {"win_prob": round(win_prob, 4)}
    if win_prob >= 0.70:
        return {**base, "label": "GANANCIA_PROYECTADA_ALTA",
                "evidence": "VPP real 87.5% sobre 8 trades históricos", "n": 8}
    if win_prob >= 0.65:
        return {**base, "label": "GANANCIA_PROYECTADA",
                "evidence": "VPP real 73.7% sobre 19 trades históricos", "n": 19}
    if win_prob >= NEUTRO_FLOOR:
        return {**base, "label": "NEUTRO",
                "evidence": "VPP ≈ win_rate global (0.59) — sin selectividad medida", "n": 0}
    return {**base, "label": "RIESGOSA_SIN_APOYO",
            "evidence": "cola baja sin selectividad medida — sin apoyo estadístico", "n": 0}


def _cache_date() -> Optional[pd.Timestamp]:
    """Fecha de la rueda más nueva presente en el cache OHLCV (max over files).

    Solo revisa los tickers del universo canónico (SYMBOLS + MARKET_TICKERS),
    no todos los .parquet del cache — así no confunde artefactos de trials
    (baseline_clean, factor_panel, capital_usage, etc.) con símbolos reales.
    """
    best = None
    for ticker in SYMBOLS + MARKET_TICKERS:
        path = os.path.join(_cache_dir(), f"{ticker}.parquet")
        if not os.path.exists(path):
            continue
        try:
            idx = pd.read_parquet(path, columns=["Close"]).index
            if len(idx) == 0:
                continue
            ts = pd.Timestamp(idx.max())
            best = ts if best is None else max(best, ts)
        except Exception:
            continue
    return best


def _cache_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cache")


def _staleness(today: pd.Timestamp, last_cache: Optional[pd.Timestamp]) -> Dict:
    if last_cache is None:
        return {"stale": True, "last_cache": None, "business_days_behind": None}
    bd_behind = len(pd.bdate_range(last_cache.normalize(), today)) - 1
    return {
        "stale": bd_behind > MAX_STALE_BD,
        "last_cache": last_cache.date().isoformat(),
        "business_days_behind": int(bd_behind),
    }


def _load_context_sync():
    """Idéntico a decision._load_context (misma fuente de verdad). SÍNCRONO Y
    PESADO a propósito (red vía yfinance en download_data si el cache tiene
    >7 días de atraso, refit de calibradores sobre ~2 años) — nunca se llama
    directo desde un handler async. Ver _get_context()."""
    from app.core.backtest_engine import BacktestEngine
    from app.core.signal_engine import SignalEngine

    market_data = _load_market_data()
    price_data = _load_price_data()
    today = pd.Timestamp.now().normalize()
    regime = _fit_regime(market_data)
    regime_state = int(regime["state"])
    engine = BacktestEngine(initial_capital=25000)
    signal_engine = SignalEngine(engine.regime_classifier)
    calibrator, conformal = _fit_calibrators(price_data, today)
    return price_data, today, regime, regime_state, signal_engine, calibrator, conformal


# Cache en memoria + offload a threadpool (HANDOFF 2026-08-19, bug "sin señal"):
# _load_context_sync corría síncrono dentro de `async def` — bloqueaba el ÚNICO
# event loop, así que hasta /health (que no toca esto) quedaba colgado detrás.
# TTL 5 min: el universo de 102 símbolos no cambia más rápido que eso para este
# uso de solo-lectura. El lock asyncio evita manada (varias requests concurrentes
# disparando el mismo refit caro a la vez) — la primera hace el trabajo, las
# demás esperan sin bloquear el loop y reciben el mismo resultado cacheado.
#
# Cache de tickets del universo: el loop de ~102 tickets (generate_signal × 102
# ≈ 174s) es una FUNCIÓN PURA del contexto (price_data, regime_state, calibradores).
# Si el contexto no ha cambiado, los tickets no cambian — cachearlos con el mismo
# TTL evita re-computar el loop en cada request (3:20 caliente → ~0.1s).
# Se invalidan automáticamente cuando el contexto se recarga (comparando timestamps).
_CONTEXT_CACHE_TTL_SECONDS = 300
_context_lock = asyncio.Lock()
_context_cache: Optional[tuple] = None
_context_cache_time: float = 0.0
_tickets_lock = asyncio.Lock()
_tickets_cache: Optional[list] = None
_tickets_cache_time: float = 0.0
_tickets_cache_ctx_time: float = 0.0


async def _get_context():
    global _context_cache, _context_cache_time
    async with _context_lock:
        now = time.monotonic()
        if _context_cache is not None and (now - _context_cache_time) < _CONTEXT_CACHE_TTL_SECONDS:
            return _context_cache
        _context_cache = await run_in_threadpool(_load_context_sync)
        _context_cache_time = time.monotonic()
        return _context_cache


async def _get_tickets(price_data, today, regime_state, signal_engine, calibrator, conformal,
                       ctx_gen: float):
    """Tickets del universo con cache de TTL — evita el loop de ~174s por request.

    Los tickets son función pura del contexto (price_data + regime_state +
    calibradores): si el contexto cacheado no cambió, los tickets calculados hace
    <TTL siguen siendo válidos.

    `ctx_gen` es `_context_cache_time` al momento de obtener el contexto en
    `advisor_universe`. Se guarda como la generación de contexto de estos tickets.
    Si el contexto se recarga entre la obtención y el cómputo de tickets, o durante
    el cómputo (174s de threadpool), la generación guardada no coincidirá con
    `_context_cache_time` en la próxima request → recálculo automático.

    Lock propio para no bloquear /symbol (que solo usa el contexto) mientras el
    universo re-computa su loop.
    """
    global _tickets_cache, _tickets_cache_time, _tickets_cache_ctx_time
    async with _tickets_lock:
        now = time.monotonic()
        if (
            _tickets_cache is not None
            and _tickets_cache_ctx_time == ctx_gen
            and (now - _tickets_cache_time) < _CONTEXT_CACHE_TTL_SECONDS
        ):
            return _tickets_cache
        _tickets_cache = await run_in_threadpool(
            _build_tickets_sync, price_data, today, regime_state,
            signal_engine, calibrator, conformal,
        )
        _tickets_cache_time = time.monotonic()
        _tickets_cache_ctx_time = ctx_gen
        return _tickets_cache


def _build_tickets_sync(price_data, today, regime_state, signal_engine, calibrator, conformal):
    """Construye todos los tickets del universo en un solo thread serial.

    Corre en el threadpool de Starlette (run_in_threadpool) para NO bloquear
    el event loop durante los ~225s de cómputo serial (102 símbolos).

    Elimina la redundancia de calculate_all_indicators para los que pasan
    gate: generate_signal ya computa los indicadores, y se reusan para
    dist_ema50/dist_ema200. Para los que no pasan gate (sig=None), mantiene
    el cálculo de EMAs para preservar el payload (mismo output que el original).
    """
    tickets = []
    for symbol, df in price_data.items():
        sig = signal_engine.generate_signal(df, symbol, regime_state)
        t = _compute_ticket(symbol, df, regime_state, today, signal_engine, calibrator, conformal,
                            sig=sig, sig_evaluated=True)
        t["projected"] = _projected_label(t["win_prob"], calibrator.is_fitted)
        close = round(float(df["close"].iloc[-1]), 2)
        t["last_close"] = close
        t["last_close_date"] = df.index[-1].date().isoformat()
        if sig is not None:
            # generate_signal ya computó calculate_all_indicators — reusamos
            ind = sig["indicators"]
            ema50 = float(ind["ema50"])
            ema200 = float(ind["ema200"])
        else:
            # Fuera de gate: SOLO las 2 EMAs necesarias para dist_ema en el payload.
            # ema() es exactamente lo que calcula calculate_all_indicators para
            # ema50/ema200 (ewm span adjust=False) — verificado idéntico en los 102
            # símbolos del universo — pero sin pagar los ~30 indicadores restantes
            # (~0.95s -> ~0.001s por símbolo).
            ema50 = float(ema(df.close, 50).iloc[-1])
            ema200 = float(ema(df.close, 200).iloc[-1])
        t["dist_ema50"] = round(close / ema50 - 1.0, 4) if ema50 and not np.isnan(ema50) else None
        t["dist_ema200"] = round(close / ema200 - 1.0, 4) if ema200 and not np.isnan(ema200) else None
        tickets.append(t)
    return tickets


@router.get("/universe")
async def advisor_universe():
    """Mesa consolidada: ticket por activo + etiqueta proyectada + transición,
    ordenado como decision.py (INVERTIR -> VIGILAR -> NO_INVERTIR, win_prob desc).

    A diferencia de /api/decision/universe (que persiste estados en cada llamada,
    efecto colateral), este endpoint es SOLO LECTURA: no escribe decision_states.
    La persistencia sigue en decision.py donde siempre estuvo.
    """
    try:
        price_data, today, regime, regime_state, signal_engine, calibrator, conformal = await _get_context()
        ctx_gen = _context_cache_time  # generación del contexto que obtuvimos

        # Tickets cacheados por TTL (mismo del contexto, 300s): como dependen
        # solo del contexto (price_data, regime_state, calibradores), son una
        # función pura. En cache caliente la segunda llamada pasa de 200s → ~0.1s.
        # La copia superficial evita que sort+transition contamine el cache compartido.
        tickets = [dict(t) for t in await _get_tickets(
            price_data, today, regime_state, signal_engine, calibrator, conformal, ctx_gen,
        )]

        prior = _latest_prior_states(_load_states_history(), today)
        for t in tickets:
            t["transition"] = _transition(t["symbol"], t["state"], prior)

        tickets.sort(
            key=lambda t: (_STATE_RANK.get(t["state"], 0),
                           t["win_prob"] if t["win_prob"] is not None else -1.0),
            reverse=True,
        )

        blocked_reason = None
        if regime_state == 3:
            blocked_reason = (
                "Régimen de mercado DEFLATION (estado 3): el motor bloquea entradas "
                "nuevas por diseño — todos los tickets quedan en NO_INVERTIR."
            )

        return {
            "as_of": today.date().isoformat(),
            "regime": {
                "state": regime_state,
                "name": regime["state_name"],
                "confidence": round(float(regime.get("confidence", 0.0)), 4),
            },
            "blocked_reason": blocked_reason,
            "staleness": _staleness(today, _cache_date()),
            "honesty_badge": (
                "Apoyo a decisión — sin señal comercial validada. "
                "Las etiquetas proyectadas se basan en la selectividad medida del win_prob "
                "(muestra n=8-19 en la cola alta), no son predicciones."
            ),
            "risk_params": {
                "absolute_ceiling": settings.ABSOLUTE_CEILING,
                "risk_per_trade": settings.RISK_PER_TRADE,
                "max_position_pct": settings.MAX_POSITION_PCT,
            },
            "states": tickets,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando universo advisor: {str(e)}")


@router.get("/theses")
async def advisor_theses():
    """Exit Thesis Monitor: para cada símbolo con snapshot de entrada (tesis),
    compara la tesis de entrada contra el estado actual.

    La tesis de entrada es la foto del momento en que un símbolo pasó a
    INVERTIR: qué gates pasaron, win_prob, score, entry_price, stop_loss,
    take_profit, régimen. Se sale cuando se pierde la tesis (filosofía del
    usuario: perder poco > ganar mucho).

    Snapshot persistido en decision_theses.json (archivo aparte, no rompe
    decision_states.json). Escritura atómica (temp+rename) igual que
    trial_registry._write.

    Este endpoint es SOLO LECTURA respecto a la tesis; si el estado actual
    de un símbolo es INVERTIR y no tiene snapshot, lo CREA (captura la foto).
    """
    try:
        price_data, today, regime, regime_state, signal_engine, calibrator, conformal = await _get_context()

        current = {}
        for symbol, df in price_data.items():
            t = _compute_ticket(symbol, df, regime_state, today, signal_engine, calibrator, conformal)
            t["last_close"] = round(float(df["close"].iloc[-1]), 2)
            current[symbol] = t

        theses = _load_theses()

        out = []
        for symbol, th in theses.items():
            if symbol not in current:
                continue
            cur = current[symbol]
            out.append(_evaluate_thesis(symbol, th, cur))

        # Captura snapshot para símbolos INVERTIR sin tesis registrada.
        new_snapshots = False
        for symbol, t in current.items():
            if t["state"] == "INVERTIR" and symbol not in theses:
                theses[symbol] = _snapshot_thesis(t, today)
                new_snapshots = True
        if new_snapshots:
            _persist_theses(theses)

        return {
            "as_of": today.date().isoformat(),
            "theses": out,
            "note": (
                "Tesis = foto de la entrada. Se degrada si algún gate de la entrada "
                "ya no se sostiene o el precio cruza la zona de salida. Filosofía: "
                "perder poco importa más que ganar mucho."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en thesis monitor: {str(e)}")


@router.get("/evidence")
async def advisor_evidence():
    """Footer de confianza: resumen del ledger de trials (fuente de verdad:
    trial_registry, no hardcodeado)."""
    try:
        entries = trial_registry.all_trials()
        by_family: Dict[str, List[Dict]] = {}
        for e in entries:
            by_family.setdefault(e["familia"], []).append(e)

        families = []
        for fam, es in by_family.items():
            raw_umbral = es[-1]["umbral_aplicado"]
            try:
                umbral = round(float(raw_umbral), 5)
            except (TypeError, ValueError):
                umbral = raw_umbral
            families.append({
                "familia": fam,
                "n_consumidos": trial_registry.consumed_budget(fam),
                "umbral_aplicado_ultimo": umbral,
                "ultimo_veredicto": es[-1]["veredicto"],
                "ultima_seccion": es[-1]["seccion_doc"],
                "n_trials_en_ledger": len(es),
            })

        recent = [
            {
                "id": e["id"],
                "fecha": e["fecha"],
                "familia": e["familia"],
                "veredicto": e["veredicto"],
                "seccion": e["seccion_doc"],
            }
            for e in entries[-5:]
        ][::-1]

        return {
            "total_trials": len(entries),
            "families": families,
            "recent": recent,
            "note": (
                "Cada trial es una hipótesis pre-registrada con umbral Bonferroni. "
                "Ninguna señal comercial validada a la fecha: el dashboard es apoyo "
                "a decisión, no un generador de señales."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo ledger: {str(e)}")


@router.get("/{symbol}")
async def advisor_symbol(symbol: str):
    """Detalle de un símbolo: OHLCV EOD (para chart), overlays del motor,
    plan de salida, M2, fundamentals EDGAR o null honesto, etiqueta proyectada."""
    try:
        price_data, today, regime, regime_state, signal_engine, calibrator, conformal = await _get_context()
        symbol = symbol.upper()

        if symbol not in price_data:
            raise HTTPException(status_code=404, detail=f"Activo {symbol} no está en el universo de datos")

        sig = signal_engine.generate_signal(price_data[symbol], symbol, regime_state)
        ticket = _compute_ticket(symbol, price_data[symbol], regime_state, today,
                                 signal_engine, calibrator, conformal, sig=sig)
        ticket["projected"] = _projected_label(ticket["win_prob"], calibrator.is_fitted)

        prior = _latest_prior_states(_load_states_history(), today)
        ticket["transition"] = _transition(ticket["symbol"], ticket["state"], prior)
        ticket["exit_plan"] = _exit_plan(regime_state)

        df = price_data[symbol]
        ind = calculate_all_indicators(df.copy())
        # OHLCV + overlays: solo últimas 400 ruedas para no inflar el payload.
        # calculate_all_indicators hace dropna() (warmup de ema200) -> ind puede
        # ser más corto que df: se realinea por fecha, nunca por posición.
        n = min(400, len(df))
        window = df.iloc[-n:]
        wind = ind.reindex(window.index)
        bars = []
        for i, (idx, row) in enumerate(window.iterrows()):
            ema50_v = wind["ema50"].iloc[i]
            ema200_v = wind["ema200"].iloc[i]
            bars.append({
                "date": idx.date().isoformat(),
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
                "ema50": round(float(ema50_v), 4) if not pd.isna(ema50_v) else None,
                "ema200": round(float(ema200_v), 4) if not pd.isna(ema200_v) else None,
            })
        ticket["ohlcv"] = bars
        ticket["last_close_date"] = df.index[-1].date().isoformat()

        # Fundamentals: EDGAR si hay cobertura, Si no null honesto (NUNCA inventar).
        fund = get_edgar_fundamentals(symbol)
        ticket["fundamentals"] = fund
        ticket["fundamentals_coverage"] = "edgar" if fund is not None else "sin_cobertura_edgar"

        return {
            "as_of": today.date().isoformat(),
            "regime": {
                "state": regime_state,
                "name": regime["state_name"],
                "confidence": round(float(regime.get("confidence", 0.0)), 4),
            },
            "blocked_reason": (
                "Régimen de mercado DEFLATION (estado 3): el motor bloquea entradas nuevas."
                if regime_state == 3 else None
            ),
            "state": ticket,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando detalle de {symbol}: {str(e)}")


# --- Exit Thesis Monitor: tesis de entrada vs estado actual ---

def _theses_path() -> str:
    return os.path.join(os.path.dirname(DECISION_STATES_PATH), "decision_theses.json")


def _load_theses() -> Dict[str, Dict]:
    path = _theses_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _persist_theses(theses: Dict[str, Dict]) -> None:
    path = _theses_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(theses, fh, indent=2, default=str)
    os.replace(tmp, path)


def _snapshot_thesis(ticket: Dict, today: pd.Timestamp) -> Dict:
    """Foto del momento de entrada (solo campos del ticket reales)."""
    return {
        "entry_date": today.date().isoformat(),
        "score": ticket.get("score"),
        "win_prob": ticket.get("win_prob"),
        "entry_price": ticket.get("entry_price"),
        "stop_loss": ticket.get("stop_loss"),
        "take_profit": ticket.get("take_profit"),
        "gates": ticket.get("gates"),
    }


def _evaluate_thesis(symbol: str, th: Dict, cur: Dict) -> Dict:
    """Compara la tesis de entrada contra el estado actual del símbolo.

    Reglas (filosofía del usuario, pre-registradas en la UI):
      - Si el estado actual ya no es INVERTIR y antes lo era -> la tesis se
        degradó o rompió según la razón.
      - Si el precio cruzó el stop_loss o el take_profit -> TESIS_ROTA
        (mecánica del motor ya habría salido).
      - Si algún gate de la entrada ya no pasa -> TESIS_DEGRADADA.
      - En otro caso -> TESIS_VIGENTE.
    """
    reasons = []

    if cur["state"] != "INVERTIR":
        reasons.append(f"estado actual {cur['state']}: {cur.get('reason', '')}")

    last_close = cur.get("last_close") if "last_close" in cur else None
    # cur viene de _compute_ticket: tiene entry/stop/tp corrientes. Usamos los
    # de la tesis como referencia de la entrada real (no los recalculados).
    ref_stop = th.get("stop_loss")
    ref_tp = th.get("take_profit")
    if last_close is not None and ref_stop is not None and last_close <= ref_stop:
        reasons.append(f"precio {last_close} cruzó stop de tesis {ref_stop}")
    if last_close is not None and ref_tp is not None and last_close >= ref_tp:
        reasons.append(f"precio {last_close} alcanzó take-profit de tesis {ref_tp}")

    # Gates de la entrada vs ahora: si la entrada exigía trend_ok y ahora no, degradó.
    th_gates = th.get("gates") or {}
    cur_gates = cur.get("gates") or {}
    gate_diffs = []
    for key in ("trend_ok", "adx", "rsi", "volume_ratio"):
        if key in th_gates and key in cur_gates:
            if key == "trend_ok":
                if th_gates[key] and not cur_gates[key]:
                    gate_diffs.append(key)
            else:
                try:
                    if th_gates[key] is not None and cur_gates[key] is not None and cur_gates[key] < th_gates[key]:
                        gate_diffs.append(key)
                except (TypeError, ValueError):
                    pass
    if gate_diffs:
        reasons.append("gates de entrada degradados: " + ", ".join(gate_diffs))

    if reasons:
        status = "TESIS_ROTA" if any("cruzó stop" in r or "take-profit" in r or "NO_INVERTIR" in r for r in reasons) else "TESIS_DEGRADADA"
    else:
        status = "TESIS_VIGENTE"

    return {
        "symbol": symbol,
        "status": status,
        "entry": th,
        "current_state": cur.get("state"),
        "current_win_prob": cur.get("win_prob"),
        "current_last_close": last_close,
        "reasons": reasons,
    }
