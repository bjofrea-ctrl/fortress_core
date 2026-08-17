"""API routes — mesa de decisión del broker (broker decision desk).

GET /api/decision/universe — ticket de decisión por activo del universo:
- state = f(gate, win_prob, régimen, abstención M2), regla compuesta exacta:
  régimen 3 (DEFLATION) bloquea entradas nuevas -> NO_INVERTIR con razón
  "régimen bloquea entradas"; gate técnico fallido (generate_signal None) ->
  NO_INVERTIR con razón "no pasa gate técnico"; win_prob calibrado (Platt)
  < 0.50 -> NO_INVERTIR; 0.50 <= win_prob < 0.60 -> VIGILAR; win_prob >= 0.60
  -> INVERTIR, salvo que M2 (conformal split, alpha=0.10) se abstenga
  (intervalo demasiado ancho) -> se degrada a VIGILAR con razón "M2
  abstención (intervalo muy ancho)".
- Cada ticket expone TODAS las mediciones verificadas (score, win_prob,
  entrada/stop/target/payoff/ATR, intervalo M2, factores y gates) — el
  humano ve la evidencia completa detrás del veredicto, no un resultado
  sin respaldo.
- Transición contra el estado registrado del día hábil anterior
  (data/cache/decision_states.json): NUEVO (sin registro previo),
  MEJORA, DETERIORO o SIN_CAMBIO.
- Solo datos actuales (sin lookahead): today = now().normalize() y toda la
  calibración usa el mismo pipeline walk-forward de opportunities.py.

GET /api/decision/{symbol} — mismo ticket para un solo activo + plan de
salida completo (los 4 mecanismos del motor) e indicadores crudos.
"""

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from app.api.routes.opportunities import (
    SYMBOLS,
    DATA_START,
    HISTORY_START,
    MARKET_TICKERS,
    _exit_plan,
    _fit_calibrator,
    _fit_regime,
    _load_market_data,
    _load_price_data,
)
from app.core.backtest_engine import BacktestEngine
from app.core.conformal import ConformalAbstentionEngine
from app.core.probabilistic_engine import ProbabilityCalibrator
from app.core.signal_engine import SignalEngine

router = APIRouter(prefix="/api/decision", tags=["decision"])

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cache")
DECISION_STATES_PATH = os.path.join(CACHE_DIR, "decision_states.json")

_STATE_RANK = {"NO_INVERTIR": 0, "VIGILAR": 1, "INVERTIR": 2}


def _state_rule(regime_state: int, sig: Optional[Dict], win_prob: Optional[float],
                m2: Optional[Dict]) -> Tuple[str, str]:
    """Regla compuesta del contrato de diseño — el veredicto y su razón."""
    if regime_state == 3:
        return "NO_INVERTIR", "régimen bloquea entradas"
    if sig is None:
        return "NO_INVERTIR", "no pasa gate técnico"
    if win_prob is None:
        return "NO_INVERTIR", "sin win_prob calibrado (calibración insuficiente)"
    if win_prob < 0.50:
        return "NO_INVERTIR", f"win_prob calibrado {win_prob:.4f} < 0.50"
    if win_prob < 0.60:
        return "VIGILAR", f"win_prob calibrado en zona de vigilancia ({win_prob:.4f})"
    if m2 is not None and m2["abstenerse"]:
        return "VIGILAR", "M2 abstención (intervalo muy ancho)"
    return "INVERTIR", "gate + win_prob >= 0.60 + M2 operativo"


def _fit_calibrators(price_data, today) -> Tuple[ProbabilityCalibrator, Optional[ConformalAbstentionEngine]]:
    """Mismo pipeline que opportunities._fit_calibrator (replay histórico a
    20d, ventana móvil de ~2 años), y sobre el MISMO set de calibración se
    ajusta M2 (ConformalAbstentionEngine, alpha=0.10). Con n < 30 M2 no se
    calibra (m2=None): la garantía conforme necesita masa en la cola."""
    engine = BacktestEngine(initial_capital=25000)
    indicators_cache = {s: df for s, df in price_data.items() if len(df) > 220}
    refit_start = today - pd.Timedelta(days=730)
    scores, outcomes = engine._build_calibration_dataset(
        indicators_cache, today, update_bayesian=False, train_start_date=refit_start
    )

    calibrator = ProbabilityCalibrator(method="platt")
    if len(scores) >= 20:
        calibrator.fit(scores, outcomes)

    conformal = None
    if len(scores) >= 30:
        conformal = ConformalAbstentionEngine(alpha=0.10)
        conformal.calibrate(scores, outcomes)
    return calibrator, conformal


def _compute_ticket(symbol: str, df, regime_state: int, today, signal_engine: SignalEngine,
                    calibrator: ProbabilityCalibrator,
                    conformal: Optional[ConformalAbstentionEngine],
                    sig: Optional[Dict] = None) -> Dict:
    """Ticket de decisión completo para un activo: gate, win_prob, M2 y el
    veredicto compuesto con su razón. Sin lookahead: solo la última fila.
    `sig` permite pasar una señal ya calculada (endpoint por símbolo, que
    además expone los indicadores crudos)."""
    if sig is None:
        sig = signal_engine.generate_signal(df, symbol, regime_state)

    win_prob = None
    if sig is not None and calibrator.is_fitted:
        win_prob = float(calibrator.predict(np.array([sig["score"]]))[0])

    m2 = None
    if sig is not None and conformal is not None:
        pred = conformal.predict(sig["score"])
        m2 = {
            "point_estimate": round(float(pred.point_estimate), 4),
            "lower": round(float(pred.lower), 4),
            "upper": round(float(pred.upper), 4),
            "abstenerse": bool(pred.abstenerse),
            "razon": pred.razon,
        }

    state, reason = _state_rule(regime_state, sig, win_prob, m2)

    gates = None
    if sig is not None:
        ind = sig["indicators"]
        gates = {
            "trend_ok": bool(ind["close"] > ind["ema50"] > ind["ema200"]),
            "adx": round(ind["adx14"], 2),
            "rsi": round(ind["rsi14"], 2),
            "volume_ratio": round(ind["volume_ratio"], 2),
        }

    return {
        "symbol": symbol,
        "state": state,
        "reason": reason,
        "score": round(float(sig["score"]), 4) if sig is not None else None,
        "win_prob": round(win_prob, 4) if win_prob is not None else None,
        "entry_price": round(float(sig["entry_price"]), 2) if sig is not None else None,
        "stop_loss": round(float(sig["stop_loss"]), 2) if sig is not None else None,
        "take_profit": round(float(sig["take_profit"]), 2) if sig is not None else None,
        "payoff_ratio": round(float(sig["payoff_ratio"]), 2) if sig is not None else None,
        "atr": round(float(sig["atr"]), 2) if sig is not None else None,
        "m2": m2,
        "factors": {k: round(float(v), 4) for k, v in sig["factors"].items()} if sig is not None else None,
        "gates": gates,
    }


def _load_states_history() -> List[Dict]:
    if not os.path.exists(DECISION_STATES_PATH):
        return []
    try:
        with open(DECISION_STATES_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _latest_prior_states(history: List[Dict], today) -> Dict:
    """Estados del día registrado más reciente ANTERIOR a hoy (nunca el de
    hoy mismo — la transición se computa contra el día hábil previo)."""
    prior = [e for e in history if str(e.get("as_of", "")) < today.isoformat()]
    if not prior:
        return {}
    latest = max(prior, key=lambda e: str(e.get("as_of", "")))
    return latest.get("states", {}) if isinstance(latest, dict) else {}


def _transition(symbol: str, state: str, prior_states: Dict) -> str:
    prev = prior_states.get(symbol)
    if prev is None:
        return "NUEVO"
    cur = _STATE_RANK.get(state, 0)
    old = _STATE_RANK.get(prev, 0)
    if cur > old:
        return "MEJORA"
    if cur < old:
        return "DETERIORO"
    return "SIN_CAMBIO"


def _persist_states(today, states: Dict[str, str]) -> None:
    """Append del día a decision_states.json (reemplaza la entrada del mismo
    día si ya existía — repetir el endpoint no duplica el registro)."""
    history = _load_states_history()
    entry = {"as_of": today.isoformat(), "states": states}
    history = [e for e in history if e.get("as_of") != today.isoformat()]
    history.append(entry)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(DECISION_STATES_PATH, "w") as f:
        json.dump(history, f, indent=2, default=str)


def _load_context():
    """Datos de mercado, precios, régimen y calibración — pipeline idéntico
    al de opportunities.py (mismas fuentes, sin inventar datos)."""
    market_data = _load_market_data()
    price_data = _load_price_data()
    today = pd.Timestamp.now().normalize()
    regime = _fit_regime(market_data)
    regime_state = int(regime["state"])
    engine = BacktestEngine(initial_capital=25000)
    signal_engine = SignalEngine(engine.regime_classifier)
    calibrator, conformal = _fit_calibrators(price_data, today)
    return price_data, today, regime, regime_state, signal_engine, calibrator, conformal


@router.get("/universe")
async def decision_universe():
    """La mesa completa: ticket por activo, ordenado INVERTIR -> VIGILAR ->
    NO_INVERTIR (win_prob desc dentro de cada grupo)."""
    try:
        price_data, today, regime, regime_state, signal_engine, calibrator, conformal = _load_context()

        tickets = [
            _compute_ticket(symbol, df, regime_state, today, signal_engine, calibrator, conformal)
            for symbol, df in price_data.items()
        ]

        prior = _latest_prior_states(_load_states_history(), today)
        for t in tickets:
            t["transition"] = _transition(t["symbol"], t["state"], prior)

        tickets.sort(
            key=lambda t: (_STATE_RANK.get(t["state"], 0),
                           t["win_prob"] if t["win_prob"] is not None else -1.0),
            reverse=True,
        )

        _persist_states(today, {t["symbol"]: t["state"] for t in tickets})

        blocked_reason = None
        if regime_state == 3:
            blocked_reason = (
                "Régimen de mercado DEFLATION (estado 3): el motor bloquea entradas "
                "nuevas por diseño — todos los tickets quedan en NO_INVERTIR, la "
                "mesa no emite entradas hoy."
            )

        return {
            "as_of": today.date().isoformat(),
            "regime": {
                "state": regime_state,
                "name": regime["state_name"],
                "confidence": round(float(regime.get("confidence", 0.0)), 4),
            },
            "blocked_reason": blocked_reason,
            "states": tickets,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando mesa de decisión: {str(e)}")


@router.get("/{symbol}")
async def decision_symbol(symbol: str):
    """Ticket de un solo activo: mismo cálculo + plan de salida (4
    mecanismos) e indicadores crudos. 404 si el activo no está en el
    universo de datos."""
    try:
        price_data, today, regime, regime_state, signal_engine, calibrator, conformal = _load_context()

        if symbol not in price_data:
            raise HTTPException(status_code=404, detail=f"Activo {symbol} no está en el universo de datos")

        sig = signal_engine.generate_signal(price_data[symbol], symbol, regime_state)
        ticket = _compute_ticket(symbol, price_data[symbol], regime_state, today,
                                 signal_engine, calibrator, conformal, sig=sig)
        prior = _latest_prior_states(_load_states_history(), today)
        ticket["transition"] = _transition(ticket["symbol"], ticket["state"], prior)
        ticket["exit_plan"] = _exit_plan(regime_state)
        ticket["indicators"] = None
        if sig is not None:
            ind = sig["indicators"]
            ticket["indicators"] = {
                "close": round(float(ind["close"]), 2),
                "ema50": round(float(ind["ema50"]), 2),
                "ema200": round(float(ind["ema200"]), 2),
                "adx14": ticket["gates"]["adx"],
                "rsi14": ticket["gates"]["rsi"],
                "volume_ratio": ticket["gates"]["volume_ratio"],
            }

        blocked_reason = None
        if regime_state == 3:
            blocked_reason = (
                "Régimen de mercado DEFLATION (estado 3): el motor bloquea entradas "
                "nuevas por diseño."
            )

        return {
            "as_of": today.date().isoformat(),
            "regime": {
                "state": regime_state,
                "name": regime["state_name"],
                "confidence": round(float(regime.get("confidence", 0.0)), 4),
            },
            "blocked_reason": blocked_reason,
            "state": ticket,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando ticket de {symbol}: {str(e)}")