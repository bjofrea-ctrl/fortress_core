"""Estructura de mercado (Smart Money Concepts) — T1.3, PLAN_INTEGRACION_INDICAGENT.md.

Four structure detectors that return STATEFUL zones ("the latest active zone"),
not continuous series. Adapted from indicAgent's
``src/intelligence/archive/smc_context/`` (order_blocks.py, fair_value_gap.py,
bos_choch.py, liquidity_sweeps.py) — pure pandas/numpy, no dependencies on the
rest of indicAgent's architecture.

Why a separate module and not in ``indicators.py``: indicators.py returns one
row per bar (continuous series); these detectors return zones with state
(top/bottom, mitigated/not) — same pattern as regime_classifier.py/regime_gate.py
(modules with their own class/logic state).

Performance note (from the ticket): call the detectors ONCE per symbol per
backtest run (alongside indicators_cache), not inside the per-date loop of
backtest_engine.run() — each of these walks the whole history.

State convention: these functions return only CURRENT STATE ("latest zone");
they are not predictions and are not verified as edge either. Any promotion to
signal requires a separate pre-registered trial (the repo's non-negotiable rule).
"""
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Minimum history per detector (indicAgent's ``min_lookback`` convention):
# below this the detector returns a clean "insufficient data" dict instead of
# NaN/None silently leaking to callers.
MIN_LOOKBACK_ORDER_BLOCKS = 50
MIN_LOOKBACK_FVG = 30
MIN_LOOKBACK_BOS_CHOCH = 60
MIN_LOOKBACK_SWEEPS = 60


# ============================================================
# Swings (shared infrastructure for BOS/CHoCH and liquidity sweeps)
# ============================================================

def find_swing_highs(high: np.ndarray, neighbor: int = 5) -> List[int]:
    """Swing highs: local maxima with ``neighbor`` bars at or below on each side.

    Returns indices into the array. A plateau where several bars equal the max
    is only reported once (the leftmost index of the plateau). Boundaries
    (with fewer than `neighbor` right-hand bars) are NOT swings by design —
    they cannot be "later broken," which is what a swing is for.
    """
    n = len(high)
    swings = []
    for i in range(neighbor, n - neighbor):
        window = high[i - neighbor:i + neighbor + 1]
        if high[i] >= window.max():
            # plateau: only take the leftmost bar of an equal-value run
            if i > 0 and high[i - 1] == high[i]:
                continue
            swings.append(i)
    return swings


def find_swing_lows(low: np.ndarray, neighbor: int = 5) -> List[int]:
    """Swing lows: local minima with ``neighbor`` bars at or above on each side."""
    n = len(low)
    swings = []
    for i in range(neighbor, n - neighbor):
        window = low[i - neighbor:i + neighbor + 1]
        if low[i] <= window.min():
            if i > 0 and low[i - 1] == low[i]:
                continue
            swings.append(i)
    return swings


# ============================================================
# 1. Order Blocks
# ============================================================

def detect_order_blocks(df: pd.DataFrame, impulse_bars: int = 3,
                        min_move_pct: float = 0.003) -> Dict:
    """Adaptado de order_blocks.py de indicAgent.

    Un order block (OB) es la última vela de dirección opuesta antes de un
    impulso: >= ``impulse_bars`` velas consecutivas en la misma dirección cuyo
    movimiento total es >= ``min_move_pct`` del precio. Zona = el cuerpo de la
    vela OB [min(open,close), max(open,close)].

    - OB alcista (type=1): vela BAJISTA inmediatamente antes de un impulso
      ALCISTA — la zona se espera que actúe como soporte.
    - OB bajista (type=-1): vela ALCISTA inmediatamente antes de un impulso
      BAJISTA — la zona se espera que actúe como resistencia.

    Mitigación: una barra POSTERIOR al impulso opera DENTRO de la zona
    (overlap: low <= ob_top Y high >= ob_bottom). Se devuelve la zona MÁS
    RECIENTE con su estado real de mitigación (``ob_mitigated``); el consumidor
    (T1.4) filtra las mitigadas.

    Returns::

        {"ob_detected": bool, "ob_type": int (1|-1|0),
         "ob_top": float, "ob_bottom": float,
         "ob_strength": float (0-1, movimiento del impulso normalizado),
         "ob_mitigated": bool, "ob_distance_pct": float}

    Con historial insuficiente: ob_detected=False, ceros el resto.
    """
    empty = {"ob_detected": False, "ob_type": 0, "ob_top": float("nan"),
             "ob_bottom": float("nan"), "ob_strength": 0.0,
             "ob_mitigated": False, "ob_distance_pct": float("nan")}
    if len(df) < MIN_LOOKBACK_ORDER_BLOCKS:
        return empty

    open_ = df["open"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    n = len(df)
    up = close >= open_  # vela alcista
    last_close = close[-1]

    best = None  # (impulse_dir, ob_idx, move_abs, impulse_end)
    for i in range(impulse_bars + 1, n + 1):
        # impulso: barras i-impulse_bars .. i-1 todas en la misma dirección
        run = up[i - impulse_bars:i]
        if run.all():
            direction = 1  # impulso alcista
        elif not run.any():
            direction = -1  # impulso bajista
        else:
            continue
        move = abs(close[i - 1] - close[i - impulse_bars]) / max(close[i - impulse_bars], 1e-9)
        if move < min_move_pct:
            continue
        # vela OB: la última vela de dirección opuesta antes del impulso
        ob_idx = i - impulse_bars - 1
        if ob_idx < 0:
            continue
        if direction == 1 and up[ob_idx]:
            continue  # hace falta una vela BAJISTA antes de un impulso alcista
        if direction == -1 and not up[ob_idx]:
            continue  # hace falta una vela ALCISTA antes de un impulso bajista
        if best is None or ob_idx > best[1]:
            best = (direction, ob_idx, move, i)

    if best is None:
        return empty

    direction, ob_idx, move, impulse_end = best
    ob_top = float(max(open_[ob_idx], close[ob_idx]))
    ob_bottom = float(min(open_[ob_idx], close[ob_idx]))
    if ob_top <= ob_bottom:  # doji: la zona degenera al precio de cierre único
        ob_top = ob_bottom = float(close[ob_idx])

    # Mitigación: barras DESPUÉS del impulso (no el impulso mismo) que
    # operan dentro de la zona (overlap: low <= top Y high >= bottom)
    later_low = low[impulse_end:]
    later_high = high[impulse_end:]
    mitigated = bool(np.any((later_low <= ob_top) & (later_high >= ob_bottom)))

    strength = min(1.0, move / max(min_move_pct * 3.0, 1e-9))
    midpoint = (ob_top + ob_bottom) / 2.0
    return {
        "ob_detected": True,
        "ob_type": direction,
        "ob_top": ob_top,
        "ob_bottom": ob_bottom,
        "ob_strength": float(strength),
        "ob_mitigated": mitigated,
        "ob_distance_pct": float((last_close - midpoint) / last_close) if last_close else float("nan"),
    }


# ============================================================
# 2. Fair Value Gaps
# ============================================================

def detect_fair_value_gaps(df: pd.DataFrame, max_lookback: int = 200) -> Dict:
    """Adapted from indicAgent's fair_value_gap.py.

    3-candle imbalance: at the middle candle ``i``,
    - Bullish FVG (type=1): low[i+1] > high[i-1] → the naked zone is
      (high[i-1], low[i+1]).
    - Bearish FVG (type=-1): high[i+1] < low[i-1] → the naked zone is
      (high[i+1], low[i-1]).

    Filled = a later bar trading THROUGH the zone
    (low <= fvg_top AND high >= fvg_bottom for an open gap: a touch inside the
    zone itself). Returns the most recent unfilled (OPEN) gap, scanning up to
    ``max_lookback`` trailing middle candles.

    Returns::

        {"fvg_detected": bool, "fvg_type": int, "fvg_top": float,
         "fvg_bottom": float, "fvg_midpoint": float,
         "fvg_size_pct": float, "fvg_open_count": int}
    """
    empty = {"fvg_detected": False, "fvg_type": 0, "fvg_top": float("nan"),
             "fvg_bottom": float("nan"), "fvg_midpoint": float("nan"),
             "fvg_size_pct": float("nan"), "fvg_open_count": 0}
    if len(df) < MIN_LOOKBACK_FVG:
        return empty

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    n = len(df)
    last_close = float(df["close"].iloc[-1])

    open_gaps = []  # (middle_idx, type, top, bottom)
    lo = max(1, n - max_lookback - 1)
    for i in range(lo, n - 1):
        if low[i + 1] > high[i - 1]:
            open_gaps.append((i, 1, float(low[i + 1]), float(high[i - 1])))
        elif high[i + 1] < low[i - 1]:
            open_gaps.append((i, -1, float(low[i - 1]), float(high[i + 1])))

    # Fill check: bars STRICTLY after the forming bar (i+1) trading into the zone
    unfilled = []
    for mid_idx, fvg_type, top, bottom in open_gaps:
        later_high = high[mid_idx + 2:]
        later_low = low[mid_idx + 2:]
        touched = np.any((later_low <= top) & (later_high >= bottom))
        if not touched:
            unfilled.append((mid_idx, fvg_type, top, bottom))

    if not unfilled:
        empty["fvg_open_count"] = 0
        return empty

    mid_idx, fvg_type, top, bottom = unfilled[-1]  # the most recent open gap
    size_pct = (top - bottom) / last_close if last_close else float("nan")
    return {
        "fvg_detected": True,
        "fvg_type": fvg_type,
        "fvg_top": max(top, bottom),
        "fvg_bottom": min(top, bottom),
        "fvg_midpoint": (top + bottom) / 2.0,
        "fvg_size_pct": float(abs(size_pct)) if np.isfinite(size_pct) else float("nan"),
        "fvg_open_count": len(unfilled),
    }


# ============================================================
# 3. BOS / CHoCH
# ============================================================

def detect_bos_choch(df: pd.DataFrame, atr: Optional[pd.Series] = None,
                     neighbor: int = 5) -> Dict:
    """Adapted from indicAgent's bos_choch.py.

    BOS (Break of Structure): the latest close breaks beyond the most recent
    swing high (bullish BOS) or swing low (bearish BOS).
    CHoCH (Change of Character): a BOS in the direction OPPOSITE to the
    prevailing trend — from the last two swings: higher-highs + higher-lows =
    uptrend; lower-highs + lower-lows = downtrend.
    Strength normalized by ATR when provided (distance past the swing level).

    Returns::

        {"bos_detected": bool, "bos_direction": int, "bos_level": float,
         "bos_strength": float, "choch_detected": bool, "choch_direction": int,
         "choch_strength": float, "smc_trend_direction": int}
    """
    empty = {"bos_detected": False, "bos_direction": 0, "bos_level": float("nan"),
             "bos_strength": 0.0, "choch_detected": False, "choch_direction": 0,
             "choch_strength": 0.0, "smc_trend_direction": 0}
    if len(df) < MIN_LOOKBACK_BOS_CHOCH:
        return empty

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close_arr = df["close"].to_numpy(dtype=float)
    last_close = float(close_arr[-1])

    swing_highs = find_swing_highs(high, neighbor)
    swing_lows = find_swing_lows(low, neighbor)
    if not swing_highs or not swing_lows:
        return empty

    last_sh = swing_highs[-1]
    last_sl = swing_lows[-1]

    # Prevailing trend: from the last two swings of each kind
    trend = 0
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh = high[swing_highs[-1]] > high[swing_highs[-2]]
        hl = low[swing_lows[-1]] > low[swing_lows[-2]]
        lh = high[swing_highs[-1]] < high[swing_highs[-2]]
        ll = low[swing_lows[-1]] < low[swing_lows[-2]]
        if hh and hl:
            trend = 1
        elif lh and ll:
            trend = -1

    atr_last = float(0.0)
    if atr is not None and len(atr) and np.isfinite(atr.iloc[-1]) and atr.iloc[-1] > 0:
        atr_last = float(atr.iloc[-1])

    # BOS check: a swing must not be one of the most recent bars itself
    # (the swing needs `neighbor` bars of confirmation to the right).
    bos_direction, bos_level = 0, float("nan")
    if last_sh < len(df) - 1 and last_close > high[last_sh]:
        bos_direction, bos_level = 1, float(high[last_sh])
    elif last_sl < len(df) - 1 and last_close < low[last_sl]:
        bos_direction, bos_level = -1, float(low[last_sl])

    if bos_direction == 0:
        out = dict(empty)
        out["smc_trend_direction"] = trend
        return out

    bos_strength = abs(last_close - bos_level) / atr_last if atr_last > 0 else 0.0
    choch = (bos_direction == -1 and trend == 1) or (bos_direction == 1 and trend == -1)
    return {
        "bos_detected": True,
        "bos_direction": bos_direction,
        "bos_level": bos_level,
        "bos_strength": float(min(bos_strength, 10.0)),
        "choch_detected": bool(choch),
        "choch_direction": bos_direction if choch else 0,
        "choch_strength": float(min(bos_strength, 10.0)) if choch else 0.0,
        "smc_trend_direction": trend,
    }


# ============================================================
# 4. Liquidity Sweeps
# ============================================================

def detect_liquidity_sweeps(df: pd.DataFrame, neighbor: int = 5,
                            reclaim_bars: int = 3) -> Dict:
    """Adapted from indicAgent's liquidity_sweeps.py.

    Sweep (stop hunt): a bar whose WICK pierces a prior swing low but whose CLOSE
    stays above it (bullish sweep, type=1), or symmetrically pierces a swing
    high but closes below it (bearish sweep, type=-1). Reclaim: the next
    ``reclaim_bars`` bars close on the correct side (above the level for type=1).

    Returns::

        {"sweep_detected": bool, "sweep_type": int, "sweep_level": float,
         "sweep_depth_pct": float, "sweep_reclaimed": bool,
         "sweep_strength": float, "reclaim_velocity": float}
    """
    empty = {"sweep_detected": False, "sweep_type": 0, "sweep_level": float("nan"),
             "sweep_depth_pct": float("nan"), "sweep_reclaimed": False,
             "sweep_strength": 0.0, "reclaim_velocity": 0.0}
    if len(df) < MIN_LOOKBACK_SWEEPS:
        return empty

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close_arr = df["close"].to_numpy(dtype=float)
    n = len(df)

    swing_highs = find_swing_highs(high, neighbor)
    swing_lows = find_swing_lows(low, neighbor)
    if not swing_highs and not swing_lows:
        return empty

    best = None  # (bar, type, level, depth, reclaimed, reclaim_velocity)
    for i in range(1, n):
        # Candidate levels: swings strictly before the sweep bar
        prior_sh = [j for j in swing_highs if j < i - 1]
        prior_sl = [j for j in swing_lows if j < i - 1]
        # Bullish sweep: wick below the most recent prior swing low, close above
        if prior_sl:
            sl = prior_sl[-1]
            level = low[sl]
            if low[i] < level < close_arr[i]:
                depth = (level - low[i]) / level if level else 0.0
                end = min(i + 1 + reclaim_bars, n)
                reclaim_seg = close_arr[i + 1:end]
                reclaimed = len(reclaim_seg) == reclaim_bars and bool(
                    np.all(reclaim_seg > level))
                velocity = float((close_arr[end - 1] - level) / level) \
                    if reclaimed and len(reclaim_seg) else 0.0
                best = (i, 1, float(level), float(depth), reclaimed, velocity)
        # Bearish sweep: wick above the most recent prior swing high, close below
        if prior_sh:
            sh = prior_sh[-1]
            level = high[sh]
            if high[i] > level > close_arr[i]:
                depth = (high[i] - level) / level if level else 0.0
                end = min(i + 1 + reclaim_bars, n)
                reclaim_seg = close_arr[i + 1:end]
                reclaimed = len(reclaim_seg) == reclaim_bars and bool(
                    np.all(reclaim_seg < level))
                velocity = float((level - close_arr[end - 1]) / level) \
                    if reclaimed and len(reclaim_seg) else 0.0
                best = (i, -1, float(level), float(depth), reclaimed, velocity)

    if best is None:
        return empty

    _bar, sweep_type, level, depth, reclaimed, velocity = best
    strength = min(1.0, depth / 0.01)  # 1% depth or more = max strength
    return {
        "sweep_detected": True,
        "sweep_type": sweep_type,
        "sweep_level": level,
        "sweep_depth_pct": depth,
        "sweep_reclaimed": reclaimed,
        "sweep_strength": float(strength),
        "reclaim_velocity": velocity,
    }


# ============================================================
# Aggregated analysis (consumable by T1.4 — stop/target resolution)
# ============================================================

def analyze_market_structure(df: pd.DataFrame,
                             atr: Optional[pd.Series] = None,
                             neighbor: int = 5) -> Dict:
    """Run all four detectors on one symbol's full history (call ONCE per
    symbol per backtest run, not per date), and also derive
    ``nearest_swing_low`` / ``nearest_resistance`` relative to the last close.

    The dict shape is directly consumable by ``signal_engine::_resolve_stop`` /
    ``_resolve_target`` (per T1.4 of the plan).
    """
    if len(df) < MIN_LOOKBACK_FVG:  # shortest lookback: shorter = don't run any
        return {"order_block": {"ob_detected": False},
                "fair_value_gap": {"fvg_detected": False},
                "bos_choch": {"bos_detected": False},
                "liquidity_sweep": {"sweep_detected": False},
                "nearest_swing_low": None, "nearest_resistance": None}

    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    last_close = float(df["close"].iloc[-1])

    swing_highs = find_swing_highs(high, neighbor)
    swing_lows = find_swing_lows(low, neighbor)

    # nearest_swing_low: the highest swing low below the last close (overhead
    # stops need the nearest support underneath, not the most recent in time)
    below = [low[j] for j in swing_lows if low[j] < last_close]
    nearest_swing_low = float(max(below)) if below else None
    # nearest_resistance: the lowest swing high strictly above the last close
    above = [high[j] for j in swing_highs if high[j] > last_close]
    nearest_resistance = float(min(above)) if above else None

    return {
        "order_block": detect_order_blocks(df),
        "fair_value_gap": detect_fair_value_gaps(df),
        "bos_choch": detect_bos_choch(df, atr=atr, neighbor=neighbor),
        "liquidity_sweep": detect_liquidity_sweeps(df, neighbor=neighbor),
        "nearest_swing_low": nearest_swing_low,
        "nearest_resistance": nearest_resistance,
    }
