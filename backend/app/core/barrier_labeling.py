"""M1 — Etiquetado por barreras (DISENO_INSTRUMENTO.md §4.2, §7 etapa 1).

MOTIVO: toda la investigación del proyecto midió poder predictivo contra retorno a
horizonte fijo (`close.shift(-h)/close - 1`), pero el motor NUNCA mantiene una posición
un número fijo de días: sale por barreras (stop de régimen, techo absoluto, toma parcial
por ATR, trailing). Es decir, se midió contra un objetivo que el motor no persigue.

Este módulo produce el objetivo que SÍ persigue: simula una posición desde una fecha de
entrada aplicando las reglas de salida reales de `adaptive_risk.check_all_stops` y
devuelve qué barrera la cerró y con qué retorno.

FIDELIDAD (regla no negociable de ONBOARDING.md): las barreras acá replican
`app/core/adaptive_risk.py` verbatim, en el mismo orden de prioridad:
  1. ABSOLUTE_CEILING_BREACH  loss <= -0.12                     (settings.ABSOLUTE_CEILING)
  2. REGIME_STOP_HIT          loss <= -position_stop[régimen]   (REGIME_THRESHOLDS)
  3. PARTIAL_TP               (price-entry) >= 2.0*ATR, una vez -> vende la MITAD, sigue
  4. TRAILING_STOP            si (max-entry) > 1.5*ATR: sale si price <= max - 2.0*ATR
Si `adaptive_risk.py` cambia, este módulo queda desactualizado y sus etiquetas dejan de
ser fieles. `verify_fidelity()` existe para detectarlo (ver abajo).

TAXONOMÍA DE SALIDA (T1.6, PLAN_INTEGRACION_INDICAGENT.md): la salida por barrera
temporal (artificial, el motor no tiene time stop) se sub-clasifica en
MAX_HORIZON_PROFIT / MAX_HORIZON_LOSS / NEVER_MOVED. El ORDEN de evaluación de las
barreras del motor NO cambia; la sub-clasificación solo se aplica al outcome temporal,
para que BayesianOnlineUpdater aprenda de outcomes más granulares que el binario
won = pnl > 0.

TIMING DE EJECUCIÓN (T0.2, PLAN_INTEGRACION_INDICAGENT.md): el motor end-of-day ahora
ejecuta con `execution_lag_days=1` — la señal se decide con el cierre de 'date' pero la
compra/venda ocurre en la APERTURA de 'date+1' (primera oportunidad real de operar).
Este módulo etiqueta sobre los cierres: `label_entry` abre al cierre de `entry_index` y
cierra al cierre de la barra donde se detecta la barrera. Eso es una APROXIMACIÓN del
nuevo timing (la barrera se DETECTA igual sobre cierres, que es la fidelidad que importa
para las reglas de salida); el desfase residual —entrar en el cierre de decisión vs la
apertura siguiente del motor, y salir en el cierre de detección vs la apertura siguiente—
es una limitación declarada, no un cambio de reglas. Si se quiere replicar el precio de
ejecución del motor con exactitud hay que pasar los precios 'open' a este módulo.

LIMITACIONES DECLARADAS (antes de usar los resultados, no después):
  - Se etiqueta UNA posición hipotética aislada. Las barreras de cartera
    (PORTFOLIO_CEILING_BREACH, portfolio_stop, cooldown) dependen del estado del
    portafolio completo y no son una propiedad del par (símbolo, fecha) — quedan fuera
    a propósito.
  - La barrera temporal (`max_horizon`) NO es una regla del motor: el motor no tiene
    time stop. Es una necesidad del etiquetado (una posición tiene que terminar para
    poder etiquetarla). Se reporta aparte para poder medir cuánto pesa.
  - El régimen afecta `position_stop`. Si no se provee serie de régimen se usa el estado
    0 (stop 5%, el más permisivo). Pasar la serie real cuando M3 la tenga.
  - Timing: ver sección TIMING DE EJECUCIÓN arriba. Se opera sobre cierres diarios (la
    barrera se detecta igual que el motor); el motor ejecuta en la apertura siguiente.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

# Espejo de app/core/adaptive_risk.py — no importar de allá para que este módulo sea
# usable sobre paneles históricos sin instanciar el RiskManager con estado vivo.
REGIME_POSITION_STOP: Dict[int, float] = {0: 0.05, 1: 0.07, 2: 0.08, 3: 0.03}
ABSOLUTE_CEILING = 0.12
PARTIAL_TP_ATR_MULT = 2.0
TRAILING_ARM_ATR_MULT = 1.5
TRAILING_GAP_ATR_MULT = 2.0

# Costo por lado idéntico al pre-registrado en los trials (#10/#11/Fase 0.6):
# 0.10% comisión + 0.05% slippage. Centralizado en app/config.py
# (settings.COST_PER_SIDE); M4 lo va a reemplazar por el costo MEDIDO — se actualiza
# en un solo lugar. Este alias se mantiene para no cambiar firmas ni callers.
from app.config import settings as _settings  # noqa: E402  (import tras constantes espejo)
from app.core.signal_ledger import SignalLedger  # noqa: E402  (solo para tipado/ledger opcional)

DEFAULT_COST_PER_SIDE = _settings.COST_PER_SIDE

DEFAULT_MAX_HORIZON = 60

# --- Taxonomía de salida temporal (T1.6) ----------------------------------
# Sub-categorías de lo que antes era un solo "no tocó nada, expiró" (TIME_BARRIER).
# NEVER_MOVED_MAX_RET: umbral de "nunca se alejó significativamente del entry" —
# si la excursión máxima absoluta desde el entry no supera este retorno, la señal
# se etiqueta NEVER_MOVED (ruido), sin importar el signo del retorno neto.
MAX_HORIZON_PROFIT = "MAX_HORIZON_PROFIT"
MAX_HORIZON_LOSS = "MAX_HORIZON_LOSS"
NEVER_MOVED = "NEVER_MOVED"
NEVER_MOVED_MAX_RET = 0.02


@dataclass(frozen=True)
class BarrierOutcome:
    """Resultado de simular una posición desde una fecha de entrada."""
    entry_index: int
    exit_index: int
    bars_held: int
    exit_reason: str          # ABSOLUTE_CEILING_BREACH | REGIME_STOP_HIT | TRAILING_STOP |
                              # MAX_HORIZON_PROFIT | MAX_HORIZON_LOSS | NEVER_MOVED
    ret_gross: float          # retorno sin costos
    ret_net: float            # retorno con costos por lado
    label: int                # +1 si ret_net > 0, -1 si < 0, 0 si exactamente 0
    partial_tp_hit: bool      # si tocó la toma parcial en el camino
    hit_time_barrier: bool    # True = terminó por la barrera artificial, no por el motor


def _leg_return(entry: float, exit_price: float, cost_per_side: float) -> float:
    """Retorno de una pata comprando en `entry` y vendiendo en `exit_price`."""
    buy = entry * (1.0 + cost_per_side)
    sell = exit_price * (1.0 - cost_per_side)
    return sell / buy - 1.0


def _two_leg_return(entry: float, exit_price: float, partial_price: Optional[float],
                    cost_per_side: float) -> float:
    """Retorno de la posición completa (una o dos patas según la toma parcial).

    Si hubo toma parcial la posición son dos patas de media unidad cada una (la
    vendida en `partial_price` y el remanente en `exit_price`); si no, es una
    sola pata completa. Bruto = _two_leg_return(..., 0.0).
    """
    partial_done = partial_price is not None
    remaining = 0.5 if partial_done else 1.0
    ret = remaining * _leg_return(entry, exit_price, cost_per_side)
    if partial_done:
        ret += 0.5 * _leg_return(entry, partial_price, cost_per_side)
    return ret


def _classify_time_exit(entry: float, closes: Sequence[float], entry_index: int,
                        exit_index: int, ret_net: float) -> str:
    """Sub-clasificación del outcome temporal (T1.6).

    Solo se llama cuando NINGUNA barrera del motor disparó. El orden de
    evaluación de las barreras no cambia; acá solo se etiqueta más fino el
    resultado de la barrera temporal:
      - NEVER_MOVED: la excursión máxima absoluta desde el entry nunca superó
        NEVER_MOVED_MAX_RET (el precio no se alejó del entry: ruido).
      - MAX_HORIZON_PROFIT / MAX_HORIZON_LOSS: el precio sí se movió y la
        posición llegó al horizonte en ganancia o en pérdida (según ret_net).
    """
    max_abs_ret = 0.0
    for t in range(entry_index, exit_index + 1):
        price = float(closes[t])
        if np.isfinite(price) and price > 0:
            max_abs_ret = max(max_abs_ret, abs(price - entry) / entry)
    if max_abs_ret <= NEVER_MOVED_MAX_RET:
        return NEVER_MOVED
    return MAX_HORIZON_PROFIT if ret_net > 0 else MAX_HORIZON_LOSS


def label_entry(
    closes: Sequence[float],
    atrs: Sequence[float],
    entry_index: int,
    position_stop: float = REGIME_POSITION_STOP[0],
    max_horizon: int = DEFAULT_MAX_HORIZON,
    cost_per_side: float = DEFAULT_COST_PER_SIDE,
) -> Optional[BarrierOutcome]:
    """Simula una posición larga abierta al cierre de `entry_index`.

    Las barreras se evalúan desde la barra SIGUIENTE a la entrada — el motor abre la
    posición procesando esa barra, así que revisarla el mismo día sería lookahead.

    Devuelve None si no hay barras futuras suficientes para evaluar (borde del panel).
    """
    n = len(closes)
    if entry_index < 0 or entry_index >= n - 1:
        return None

    entry = float(closes[entry_index])
    if not np.isfinite(entry) or entry <= 0:
        return None

    last_index = min(entry_index + max_horizon, n - 1)

    partial_price: Optional[float] = None   # precio al que se vendió la mitad, si pasó
    highest = entry

    for t in range(entry_index + 1, last_index + 1):
        price = float(closes[t])
        if not np.isfinite(price):
            continue
        atr = float(atrs[t]) if np.isfinite(atrs[t]) else 0.0
        loss = (price - entry) / entry

        # 1. Techo absoluto — cierra todo lo que quede
        if loss <= -ABSOLUTE_CEILING:
            return _close(entry, price, t, entry_index, "ABSOLUTE_CEILING_BREACH",
                          partial_price, cost_per_side, False)

        # 2. Stop de régimen — cierra todo lo que quede
        if loss <= -position_stop:
            return _close(entry, price, t, entry_index, "REGIME_STOP_HIT",
                          partial_price, cost_per_side, False)

        # 3. Toma parcial: vende la MITAD una sola vez y la posición continúa
        if (atr > 0 and (price - entry) >= PARTIAL_TP_ATR_MULT * atr
                and partial_price is None):
            partial_price = price

        # 4. Trailing — se arma recién cuando el máximo superó 1.5*ATR sobre la entrada
        highest = max(highest, price)
        if atr > 0 and (highest - entry) > TRAILING_ARM_ATR_MULT * atr:
            trailing = highest - TRAILING_GAP_ATR_MULT * atr
            if price <= trailing:
                return _close(entry, price, t, entry_index, "TRAILING_STOP",
                              partial_price, cost_per_side, False)

    # Ninguna barrera del motor disparó: cierra por la barrera temporal (artificial).
    # T1.6: el outcome temporal se sub-clasifica (NEVER_MOVED vs MAX_HORIZON_*).
    exit_price = float(closes[last_index])
    net = _two_leg_return(entry, exit_price, partial_price, cost_per_side)
    reason = _classify_time_exit(entry, closes, entry_index, last_index, net)
    return _close(entry, exit_price, last_index, entry_index, reason,
                  partial_price, cost_per_side, True)


def _close(entry: float, exit_price: float, exit_index: int, entry_index: int,
           reason: str, partial_price: Optional[float],
           cost_per_side: float, hit_time: bool) -> BarrierOutcome:
    """Cierra el remanente y arma el resultado.

    Si hubo toma parcial, la posición son dos patas de media unidad cada una: la vendida
    en `partial_price` y el remanente vendido en `exit_price`. Bruto y neto se calculan
    sobre las MISMAS patas — la única diferencia es el costo.
    """
    ret_net = _two_leg_return(entry, exit_price, partial_price, cost_per_side)
    gross = _two_leg_return(entry, exit_price, partial_price, 0.0)

    partial_done = partial_price is not None
    label = 1 if ret_net > 0 else (-1 if ret_net < 0 else 0)
    return BarrierOutcome(
        entry_index=entry_index,
        exit_index=exit_index,
        bars_held=exit_index - entry_index,
        exit_reason=reason,
        ret_gross=float(gross),
        ret_net=float(ret_net),
        label=label,
        partial_tp_hit=partial_done,
        hit_time_barrier=hit_time,
    )


def _ts_key(ts) -> str:
    """Clave de fecha para el ledger: ISO si es convertible, str si no."""
    try:
        return pd.Timestamp(ts).isoformat()
    except (TypeError, ValueError):
        return str(ts)


def label_symbol(
    df: pd.DataFrame,
    regimes: Optional[Sequence[int]] = None,
    max_horizon: int = DEFAULT_MAX_HORIZON,
    cost_per_side: float = DEFAULT_COST_PER_SIDE,
    close_col: str = "close",
    atr_col: str = "atr14",
    symbol: Optional[str] = None,
    ledger: Optional["SignalLedger"] = None,
) -> pd.DataFrame:
    """Etiqueta CADA fecha de un símbolo como si se hubiera abierto posición ahí.

    `regimes` es la serie de estado HMM por fecha (0-3). Si es None se usa 0 para todo
    (stop 5%) — limitación declarada en el docstring del módulo.

    T1.6: si se pasa `ledger` (SignalLedger) se persiste una fila por señal generada
    en `fortress.db` — `symbol` es obligatorio en ese caso para armar el signal_id.
    """
    if close_col not in df.columns or atr_col not in df.columns:
        raise ValueError(f"Faltan columnas requeridas: {close_col}, {atr_col}")
    if ledger is not None and symbol is None:
        raise ValueError("symbol es requerido cuando se persiste en el ledger")

    closes = df[close_col].to_numpy(dtype=float)
    atrs = df[atr_col].to_numpy(dtype=float)
    n = len(closes)

    if regimes is None:
        stops = np.full(n, REGIME_POSITION_STOP[0])
    else:
        stops = np.array([REGIME_POSITION_STOP.get(int(r), REGIME_POSITION_STOP[0])
                          for r in regimes], dtype=float)

    rows: List[dict] = []
    for i in range(n):
        outcome = label_entry(closes, atrs, i, position_stop=float(stops[i]),
                              max_horizon=max_horizon, cost_per_side=cost_per_side)
        if outcome is None:
            continue
        if ledger is not None:
            entry_ts = df.index[i]
            ledger.record(
                signal_id=f"{symbol}__{_ts_key(entry_ts)}",
                symbol=symbol,
                entry_date=_ts_key(entry_ts),
                exit_date=_ts_key(df.index[outcome.exit_index]),
                exit_reason=outcome.exit_reason,
                pnl_r=(outcome.ret_net / stops[i]) if stops[i] > 0 else outcome.ret_net,
                regime_state=int(regimes[i]) if regimes is not None else 0,
            )
        rows.append({
            "date": df.index[i],
            "exit_date": df.index[outcome.exit_index],
            "bars_held": outcome.bars_held,
            "exit_reason": outcome.exit_reason,
            "ret_gross": outcome.ret_gross,
            "ret_net": outcome.ret_net,
            "label": outcome.label,
            "partial_tp_hit": outcome.partial_tp_hit,
            "hit_time_barrier": outcome.hit_time_barrier,
        })
    return pd.DataFrame(rows)


def summarize(labels: pd.DataFrame) -> dict:
    """Diagnóstico del etiquetado — se lee ANTES de usar las etiquetas para nada."""
    if labels.empty:
        return {"n": 0}
    return {
        "n": int(len(labels)),
        "por_barrera": labels["exit_reason"].value_counts().to_dict(),
        "pct_barrera_temporal": float(labels["hit_time_barrier"].mean()),
        "pct_toco_parcial": float(labels["partial_tp_hit"].mean()),
        "mediana_bars_held": float(labels["bars_held"].median()),
        "win_rate_neto": float((labels["label"] > 0).mean()),
        "ret_net_medio": float(labels["ret_net"].mean()),
    }


def verify_fidelity() -> dict:
    """Verifica que las reglas de barrera replican `adaptive_risk.check_all_stops`.

    Es el contrato de fidelidad del módulo (ver docstring del módulo): las
    constantes y la PRIORIDAD entre barreras deben espejar el RiskManager real.
    Si `adaptive_risk.py` cambia cualquiera de estas reglas, verify_fidelity()
    lo detecta y hay que actualizar este módulo en el mismo cambio.

    Nota (T0.2): este chequeo cubre las REGLAS de salida (lo que importa para la
    fidelidad de las etiquetas). El TIMING de ejecución del motor (entrar/salir
    en la apertura de la barra siguiente) es una dimensión distinta, declarada en
    la sección TIMING DE EJECUCIÓN del docstring.
    """
    from app.config import settings as _cfg
    from app.core import adaptive_risk

    issues = []

    # 1. Constantes espejo vs adaptive_risk
    ref_stops = {r: th["position_stop"] for r, th in adaptive_risk.REGIME_THRESHOLDS.items()}
    if ref_stops != REGIME_POSITION_STOP:
        issues.append(f"REGIME_POSITION_STOP no espeja REGIME_THRESHOLDS: {ref_stops}")

    if abs(ABSOLUTE_CEILING - _cfg.ABSOLUTE_CEILING) > 1e-12:
        issues.append(f"ABSOLUTE_CEILING ({ABSOLUTE_CEILING}) != settings.ABSOLUTE_CEILING ({_cfg.ABSOLUTE_CEILING})")

    if abs(DEFAULT_COST_PER_SIDE - _cfg.COST_PER_SIDE) > 1e-12:
        issues.append(f"DEFAULT_COST_PER_SIDE ({DEFAULT_COST_PER_SIDE}) != settings.COST_PER_SIDE ({_cfg.COST_PER_SIDE})")

    # 2. Prioridad entre barreras (escenarios representativos)
    atr = np.full(3, 50.0)
    # 2a. Techo absoluto tiene prioridad sobre el stop de régimen en la misma barra.
    bajo_techo = 100.0 * (1.0 - ABSOLUTE_CEILING - 0.03)
    out = label_entry(np.array([100.0, bajo_techo]), atr, 0, position_stop=0.05)
    if out is None or out.exit_reason != "ABSOLUTE_CEILING_BREACH":
        issues.append(f"Techo absoluto no tiene prioridad: {out.exit_reason if out else 'None'}")

    # 2b. Stop de régimen: -4% dispara el del régimen 3 (3%) pero no el del 0 (5%).
    r3 = label_entry(np.array([100.0, 96.0]), atr, 0, position_stop=REGIME_POSITION_STOP[3])
    r0 = label_entry(np.array([100.0, 96.0]), atr, 0, position_stop=REGIME_POSITION_STOP[0])
    if r3 is None or r3.exit_reason != "REGIME_STOP_HIT":
        issues.append(f"Stop régimen 3 no dispara a -4%: {r3.exit_reason if r3 else 'None'}")
    if r0 is not None and r0.exit_reason == "REGIME_STOP_HIT":
        issues.append("Stop régimen 0 dispara a -4% (debería NO disparar)")

    # 2c. Trailing: se arma recién tras superar 1.5*ATR y dispara a max - 2*ATR.
    t_out = label_entry(np.array([100.0, 102.0, 99.5]), np.full(3, 1.0), 0,
                        position_stop=0.50)
    if t_out is None or t_out.exit_reason != "TRAILING_STOP":
        issues.append(f"Trailing no dispara correctamente: {t_out.exit_reason if t_out else 'None'}")

    ok = len(issues) == 0
    return {"fidelity_ok": ok, "issues": issues}
