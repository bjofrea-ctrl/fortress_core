"""
TRIAL #18 (PLAN §45, 2026-08-24) — Stops EVT con sizing aislado: re-take de la
línea #15 neutralizando las DOS capas de inercia (Hallazgo 6). PRE-REGISTRADO y
APROBADO antes de correr (§45, revisión coordinador+Boris 2026-08-24).

Cambio vs #15: la variable EVT solo puede medirse si `shares_by_risk` es la
restricción activa del sizing. §45 fija:
  (1) Rama Kelly DESACTIVADA SIMÉTRICAMENTE en ambos brazos (replicar la rama
      no-Kelly `int(min(shares_by_risk, max_shares))`, adaptive_risk.py:121).
      NOTA: fractional_kelly=0 daría min(0,...)=0 shares — no sirve.
  (2) RISK_PER_TRADE_arm = 0.0015 en AMBOS brazos (MAX_POSITION_PCT intacto):
      umbral de binding dist > (0.0015/0.10)*price = 1.5%*price, bajo el rango
      típico de ambas distancias (2xATR 4-6%P, Hallazgo 6).
  Alcance idéntico a §20 (variante mínima): SOLO la distancia de riesgo del
  sizing; stops ejecutivos/PARTIAL_TP/trailing/CEILING intactos.

Walk-forward EVT idéntico a §20 (helpers verbatim del script #15 post-fix
Hallazgo 5): EWMA lambda=0.94 causal CON cuadrado, recalibración cada 63 hábiles,
ventana móvil 756 hábiles de z=r/sigma, u=p95%, GPD MLE loc=0, VaR_GPD(99%) McNeil,
fallback cuantil empírico si excesos<30, data desde 2015-01-01. Fallback de sizing
cuando un símbolo/fecha aún no tiene EVT vigente: distancia ATR dentro del MISMO
marco no-Kelly (cuenta aparte en activación; en #15 el fallback usaba Kelly —
inconsistencia que v2 elimina).

GATE DE ACTIVACIÓN F7 (pre-registrado): interpretable solo si shares_by_risk fue
la restricción activa en >=50% de las compras del brazo EVT en >=2/3 ventanas.
F7 falla -> NO se registra en trial_registry (no consume slot motor_signal),
intento inválido documentado. F7 pasa -> se registra sea CUMPLE o NO_CUMPLE.

Umbral leído DEL LEDGER en runtime: familia motor_signal consumido=11 -> n=12 ->
current_threshold()=0.9916666666666667. Criterio: DSR OOS >= 0.99167 en >=2/3
ventanas computables (piso >=30 trades brazo EVT); n=12 alimenta también el
Deflated Sharpe. Baseline intra-corrida bajo el motor VIGENTE (incluye
execution_lag_days=1 de T0.2, posterior a #15).

Reglas: Python 3.9 real (backend/.venv), lee SOLO cache parquet. No toca
signal_engine.py/backtest_engine.py/adaptive_risk.py/trial_registry.py en runtime
(inyección por subclase vía hook _make_risk_manager; el parche identity-cache es
intra-proceso, ver docstring de patch_signal_engine_identity_cache y F9).
INTENTO 2 (2026-08-24): intento 1 abortado sin veredicto tras ~13h solo en
baseline — generate_signal recalcula indicadores redundantes por día x símbolo
(explosión T2.3 hurst); este intento usa parche de identidad bit-idéntico
verificado en-corrida (F9). Metodología de sizing INTACTA.
Uso (UNA sola corrida):
  cd backend && .venv/bin/python -u -m scripts.trial_evt_stops_v2
Salida:
  data/cache/trial18_evt_stops_v2_<ts>.txt + parquet trades/equity por brazo
"""
import datetime
import json
import os
import threading
import time

import numpy as np
import pandas as pd
from app.core.adaptive_risk import AdaptiveRiskManager
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.trial_registry import consumed_budget, current_threshold
from scipy.stats import genpareto
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
DATA_START = "2015-01-01"
OP_START = "2019-01-01"
END = "2026-08-20"            # borde del cache verificado 2026-08-24 (sin descargas)
WINDOWS = [
    ("W1 2020-2021", "2020-01-01", "2021-12-31"),
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]
TRADE_FLOOR = 30
BATCH_DAYS = 63
CAL_WINDOW_DAYS = 756
LAMBDA = 0.94
U_QUANTILE = 0.95
VAR_LEVEL = 0.99
MIN_EXCESS = 30
RISK_PER_TRADE_ARM = 0.0015   # dial del experimento (§45): ambos brazos iguales
ACTIVATION_MIN = 0.50         # gate F7: % compras con by_risk activo
INITIAL_CAPITAL = 25000.0

# Umbral leído DEL LEDGER en runtime (§45 lo fija antes de correr)
N_FAM_CONSUMED = consumed_budget("motor_signal")
N_TRIALS_DSR = N_FAM_CONSUMED + 1
DSR_THRESHOLD = current_threshold("motor_signal")


def ewma_vol_daily(r: pd.Series, warmup: int = 60) -> pd.Series:
    """EWMA lambda=0.94 causal CON el cuadrado (regresión Hallazgo 5)."""
    r2 = r.to_numpy()
    v = float(np.var(r2[:warmup], ddof=1)) if len(r2) > warmup else float(np.var(r2, ddof=1))
    out = np.empty(len(r2))
    v = 0.0 if not np.isfinite(v) else v
    for t in range(len(r2)):
        if t > 0:
            v = LAMBDA * v + (1 - LAMBDA) * r2[t - 1] ** 2
        out[t] = np.sqrt(max(v, 1e-12))
    return pd.Series(out, index=r.index)


def calibrate_var_gpd(z: np.ndarray) -> float:
    """VaR_GPD(99%) para la cola izquierda sobre z estandarizados de la ventana."""
    z = z[np.isfinite(z)]
    L = -z
    u = float(np.quantile(L, U_QUANTILE))
    exc = L[L > u] - u
    if len(exc) < MIN_EXCESS:
        return float(np.quantile(L, VAR_LEVEL))
    shape, _, scale = genpareto.fit(exc, floc=0)
    n_excs, n_obs = len(exc), len(z)
    b = n_excs / n_obs / (1 - VAR_LEVEL)
    if abs(shape) < 1e-12 or scale <= 0:
        var = u + scale * np.log(b)
    else:
        var = u + scale / shape * (b ** shape - 1)
    return float(var)


class _NoKellyRiskManager(AdaptiveRiskManager):
    """Base común de AMBOS brazos (§45): rama Kelly desactivada simétricamente
    + RISK_PER_TRADE del experimento. Registra diagnósticos de activación."""

    def __init__(self, capital: float):
        super().__init__(capital)
        self.RISK_PER_TRADE = RISK_PER_TRADE_ARM   # dial §45, ambos brazos
        self._sizing_log = []                      # (date, symbol, active, dist, by_risk, max_shares)
        self._buys_sized = 0
        self._buys_executed = 0

    def _size_no_kelly(self, equity, price, atr, symbol, stop_distance):
        thresholds = self.get_thresholds()
        floor_dist = price * thresholds["position_stop"]
        stop_distance = max(stop_distance, floor_dist)
        shares_by_risk = (equity * self.RISK_PER_TRADE) / stop_distance
        max_shares = (equity * self.MAX_POSITION_PCT) / price
        active = "by_risk" if shares_by_risk <= max_shares else "cap"
        self._sizing_log.append({
            "date": None if self.state.current_date is None else pd.Timestamp(self.state.current_date),
            "symbol": symbol, "active": active,
            "stop_distance": float(stop_distance),
            "dist_2atr_equiv": float(max(2.0 * atr, floor_dist)),
            "floor_dist": float(floor_dist),
            "shares_by_risk": float(shares_by_risk),
            "max_shares": float(max_shares),
            "shares": int(min(shares_by_risk, max_shares)),
        })
        self._buys_sized += 1
        return int(min(shares_by_risk, max_shares))

    def compute_position_size(self, equity, price, atr, win_prob=None,
                              payoff_ratio=None, fractional_kelly=0.25, symbol=None):
        """Rama Kelly ELIMINADA (win_prob/payoff_ratio ignorados a propósito —
        desactivación simétrica §45)."""
        if atr <= 0 or price <= 0:
            return 0
        return self._size_no_kelly(equity, price, atr, symbol, 2.0 * atr)

    def register_entry(self, symbol, price, shares):
        self._buys_executed += 1
        return super().register_entry(symbol, price, shares)

    def activation_stats(self):
        n = len(self._sizing_log)
        by_risk = sum(1 for s in self._sizing_log if s["active"] == "by_risk")
        return {"compras_dimensionadas": n,
                "ejecutadas": self._buys_executed,
                "pct_by_risk_activo": (by_risk / n) if n else float("nan")}


class BaselineRiskManager(_NoKellyRiskManager):
    """Brazo baseline: stop_distance = max(2xATR, price*position_stop), sin Kelly."""


class EVTRiskManagerV2(_NoKellyRiskManager):
    """Brazo EVT: stop_distance = max(VaR_GPD(99%)_vigente x sigma_EWMA_dia,
    price*position_stop), sin Kelly. Maquinaria walk-forward verbatim del #15."""

    def __init__(self, capital: float, price_data: dict):
        super().__init__(capital)
        self._var_table: dict = {}
        self._current_date = None
        self._n_evt_buys = 0
        self._n_fallback_buys = 0
        for sym, df in price_data.items():
            close = df.sort_index()["close"]
            r = close.pct_change().dropna()
            if len(r) < CAL_WINDOW_DAYS + BATCH_DAYS:
                continue
            sig = ewma_vol_daily(r)
            z = (r / sig).to_numpy()
            dates = r.index.to_numpy()
            n = len(dates)
            rec_dates, vars_, sigs_ = [], [], []
            for i in range(CAL_WINDOW_DAYS, n, BATCH_DAYS):
                rec_dates.append(dates[i - 1])
                vars_.append(calibrate_var_gpd(z[i - CAL_WINDOW_DAYS:i]))
                sigs_.append(sig.iloc[i])
            rec_arr = np.asarray(rec_dates, dtype="datetime64[ns]")
            sig_by_date = pd.Series(sig.to_numpy(), index=r.index)
            self._var_table[sym] = rec_arr
            self._var_table[sym + "__var"] = vars_
            self._var_table[sym + "__sig"] = sig_by_date
        self._batches = sorted({d for sym in price_data for d in self._var_table.get(sym, [])})

    def _var_mult(self, symbol: str, price_date):
        rec_dates = self._var_table.get(symbol)
        if rec_dates is None:
            return None
        vars_ = self._var_table[symbol + "__var"]
        as_dt = np.datetime64(pd.Timestamp(price_date))
        idx = np.searchsorted(rec_dates, as_dt, side="left") - 1
        if idx < 0:
            return None
        return vars_[idx]

    def _sig_at_date(self, symbol: str, price_date):
        sig = self._var_table.get(symbol + "__sig")
        if sig is None:
            return None
        as_dt = np.datetime64(pd.Timestamp(price_date))
        pos = sig.index.searchsorted(as_dt, side="right") - 1
        return float(sig.iloc[pos]) if pos >= 0 else None

    def _sync_clock(self, date):
        if self._current_date != date:
            self._current_date = pd.Timestamp(date)

    def check_all_stops(self, equity, current_prices, atrs, date):
        self._sync_clock(date)
        return super().check_all_stops(equity, current_prices, atrs, date)

    def can_open_new_position(self, date):
        self._sync_clock(date)
        return super().can_open_new_position(date)

    def compute_position_size(self, equity, price, atr, win_prob=None,
                              payoff_ratio=None, fractional_kelly=0.25, symbol=None):
        if atr <= 0 or price <= 0:
            return 0
        var_mult = self._var_mult(symbol, self._current_date) if symbol else None
        sig_today = self._sig_at_date(symbol, self._current_date) if symbol else None
        if var_mult is None or sig_today is None:
            # Fallback declarado §45: distancia ATR en el MISMO marco no-Kelly
            self._n_fallback_buys += 1
            return super().compute_position_size(equity, price, atr, win_prob,
                                                 payoff_ratio, fractional_kelly, symbol)
        rec_dates = self._var_table[symbol]
        as_dt = np.datetime64(self._current_date)
        idx = np.searchsorted(rec_dates, as_dt, side="left") - 1
        assert idx >= 0, f"EVT sin recalibracion previa para {symbol} el {self._current_date}"
        assert rec_dates[idx] < as_dt, (
            f"LOOKAHEAD EVT: recalibracion {rec_dates[idx]} no es anterior a compra {self._current_date}")
        self._n_evt_buys += 1
        entry = self._sizing_log
        n0 = len(entry)
        out = self._size_no_kelly(equity, price, atr, symbol,
                                  var_mult * sig_today)
        entry[n0]["evt_term"] = float(var_mult * sig_today)
        entry[n0]["evt_calibrada"] = True
        return out


class BaselineEngine(BacktestEngine):
    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        super().__init__(initial_capital)
        self._used_rm = None

    def _make_risk_manager(self):
        rm = BaselineRiskManager(self.initial_capital)
        self._used_rm = rm
        return rm


class EVTEngineV2(BacktestEngine):
    def __init__(self, initial_capital: float = INITIAL_CAPITAL, price_data: dict = None):
        super().__init__(initial_capital)
        self._evt_price_data = price_data
        self._used_rm = None

    def _make_risk_manager(self):
        rm = EVTRiskManagerV2(self.initial_capital, self._evt_price_data)
        self._used_rm = rm
        return rm


def period_metrics(equity_curve, trades, s, e, engine):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=N_TRIALS_DSR), tr


def patch_signal_engine_identity_cache(price_data):
    """Nota de ejecución §45 (intento 2, 2026-08-24): generate_signal recalcula
    calculate_all_indicators(df.loc[:date]) en CADA día x símbolo, pero el frame
    que recibe ya viene indicatorizado (backtest_engine.py:299 construye
    indicators_cache una vez). El recálculo es redundante y tras T2.3 (hurst)
    volvió el run ~10x más caro — intento 1 abortado tras 13h solo en baseline
    (artefacto ABORTADO_trial18_evt_stops_v2_20260824_070552.txt), sin veredicto.

    Parche SOLO dentro de este proceso: identity sobre el frame ya indicatorizado.
    Equivalencia bit-idéntica por causalidad: todas las columnas son rolling/
    backward desde la primera fila del frame completo, así que calcularlas sobre
    el slice .loc[:date] o tomarlas del cache del frame completo produce los
    mismos valores fila a fila. F9 verifica esto en-corrida muestreando pares
    (símbolo, fecha): si alguna columna difiere -> assert -> aborto documentado.
    """
    import app.core.signal_engine as se

    full_indicators = {s: calculate_all_indicators(df) for s, df in price_data.items()}

    cols_check = ["close", "atr14", "rsi14", "adx14", "momentum_12_1",
                  "hurst_exponent", "realized_vol_regime", "kama_dist",
                  "hma_dist", "supertrend_side"]
    rng = np.random.default_rng(42)
    symbols_ok = [s for s in price_data if s in full_indicators]
    n_checked = 0
    for _ in range(25):
        sym = symbols_ok[int(rng.integers(len(symbols_ok)))]
        fi = full_indicators[sym]
        if len(fi) < 600:
            continue
        d = fi.index[int(rng.integers(500, len(fi)))]
        recomputed = calculate_all_indicators(price_data[sym].loc[:d])
        common = recomputed.index.intersection(fi.loc[:d].index)
        if len(common) == 0:
            continue
        tail = common[-1]
        for c in cols_check:
            a = fi.loc[tail, c]
            b = recomputed.loc[tail, c]
            assert np.isclose(float(a), float(b), rtol=1e-12, atol=1e-15), (
                f"F9 EQUIVALENCIA ROTA: {sym} {tail.date()} col={c} cache={a} vs recompute={b}")
        n_checked += 1
    assert n_checked >= 10, "F9: insuficientes pares verificados"

    def _identity(sdf):
        return sdf

    se.calculate_all_indicators = _identity
    return {"pares_verificados": n_checked,
            "columnas": cols_check,
            "ok": True}


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join("data", "cache", f"trial18_evt_stops_v2_{ts}.txt")
    json_path = os.path.join("data", "cache", f"trial18_evt_stops_v2_{ts}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    phase = ["arranque"]
    heartbeat_stop = threading.Event()

    def _heartbeat_loop():
        t0 = time.time()
        while not heartbeat_stop.wait(60):
            line = f"[heartbeat] t={int(time.time() - t0)}s | fase={phase[0]}"
            print(line, flush=True)
            with open(out_path, "a") as f:
                f.write(line + "\n")

    hb = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb.start()

    def log(msg: str = ""):
        print(msg, flush=True)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 76)
    log("TRIAL #18 (PLAN §45) — STOPS EVT CON SIZING AISLADO (pre-registrado y aprobado)")
    log(f"Universo: {len(SYMBOLS)} símbolos | data {DATA_START} -> {END} | operación {OP_START} -> {END}")
    log(f"Dial §45: RISK_PER_TRADE_arm={RISK_PER_TRADE_ARM} (AMBOS brazos), MAX_POSITION_PCT intacto")
    log("Kelly desactivado SIMÉTRICAMENTE (rama no-Kelly int(min(by_risk, cap)))")
    log("Brazo EVT: stop_distance = max(VaR_GPD(99%)_vigente x sigma_EWMA_dia, piso)")
    log("Brazo BASE: stop_distance = max(2xATR, piso) | resto del risk manager INTACTO")
    log(f"Walk-forward: recalib cada {BATCH_DAYS}d habiles, ventana {CAL_WINDOW_DAYS}d, "
        f"lambda={LAMBDA}, u=p{U_QUANTILE:.0%}, VaR p{VAR_LEVEL:.0%} | fallback empirico si <{MIN_EXCESS} excesos")
    log(f"GATE F7: pct_by_risk_activo(brazo EVT) >= {ACTIVATION_MIN:.0%} en >= 2/3 ventanas")
    log("Ledger runtime: motor_signal consumido=%d -> n=%d | current_threshold=%.16f"
        % (N_FAM_CONSUMED, N_TRIALS_DSR, DSR_THRESHOLD))
    log("Criterio: DSR OOS >= %.5f en >= 2/3 ventanas computables | piso %d trades EVT"
        % (DSR_THRESHOLD, TRADE_FLOOR))
    log("=" * 76)

    checks = {}
    market_data = load_universe(MARKET_TICKERS, DATA_START, END)
    price_data = load_universe(SYMBOLS, DATA_START, END)
    checks["F1_universo50"] = {"cargadas": len(price_data), "esperado": len(SYMBOLS),
                               "ok": len(price_data) == len(SYMBOLS)}
    log(f"\nF1 precios cargados: {len(price_data)}/{len(SYMBOLS)} ({DATA_START} -> {END})")

    # Nota de ejecución §45 intento 2: parche de identidad intra-proceso + F9
    phase[0] = "F9 equivalencia"
    checks["F9_equivalencia_identity"] = patch_signal_engine_identity_cache(price_data)
    log("F9 equivalencia identity-cache: %d pares (símbolo,fecha) bit-idénticos "
        "verificados en %d columnas" % (
            checks["F9_equivalencia_identity"]["pares_verificados"],
            len(checks["F9_equivalencia_identity"]["columnas"])))

    evt_probe = EVTRiskManagerV2(INITIAL_CAPITAL, price_data)
    mults = [v for s in SYMBOLS for v in evt_probe._var_table.get(s + "__var", [])]
    med_mult = float(np.median(mults)) if mults else float("nan")
    checks["F5_ewma_cuadrado_regresion_hallazgo5"] = {
        "n_var_mult": len(mults), "mediana_var_mult": med_mult,
        "ok": bool(np.isfinite(med_mult) and 1.0 <= med_mult <= 20.0)}
    log("F5 regresión Hallazgo 5: mediana var_mult=%.4f (rango plausible [1,20], "
        "nunca 10^3-10^5) | %d/%d símbolos calibrados | %d fechas de recalibración"
        % (med_mult, sum(1 for s in SYMBOLS if s in evt_probe._var_table),
           len(SYMBOLS), len(evt_probe._batches)))
    del evt_probe

    log("\nCorriendo brazo BASELINE_RISK (mismo motor vigente, sin Kelly)...")
    phase[0] = "baseline run"
    base_engine = BaselineEngine(initial_capital=INITIAL_CAPITAL)
    res_base = base_engine.run(
        price_data, market_data, pd.Timestamp(OP_START), pd.Timestamp(END))

    log("Corriendo brazo EVT_RISK (EVTEngineV2 walk-forward, sin Kelly)...")
    phase[0] = "EVT run"
    evt_engine = EVTEngineV2(initial_capital=INITIAL_CAPITAL, price_data=price_data)
    res_evt = evt_engine.run(
        price_data, market_data, pd.Timestamp(OP_START), pd.Timestamp(END))
    phase[0] = "metricas"

    rm_base = base_engine._used_rm
    rm_evt = evt_engine._used_rm
    log("\nAnti-lookahead: %d compras EVT dimensionadas con VaR-GPD walk-forward "
        "(assert recalibración estrictamente anterior activo en todas) | %d fallback ATR"
        % (rm_evt._n_evt_buys, rm_evt._n_fallback_buys))
    checks["F4_antileakage_y_recalibs"] = {
        "compras_evt_con_assert_ok": rm_evt._n_evt_buys,
        "fechas_recalibracion": len(rm_evt._batches),
        "ok": bool(rm_evt._n_evt_buys > 0 and len(rm_evt._batches) > 30)}

    act_base = rm_base.activation_stats()
    act_evt = rm_evt.activation_stats()
    log("Activación BASE: %s" % act_base)
    log("Activación EVT : %s" % act_evt)

    engine = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    results = {}
    gate_per_window = {}
    verdict_rows = []
    for label, s, e in WINDOWS:
        mb, trb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine)
        mv, trv = period_metrics(res_evt["equity_curve"], res_evt["trades"], s, e, engine)
        sub_base = [x for x in rm_base._sizing_log
                    if x["date"] is not None and pd.Timestamp(s) <= x["date"] <= pd.Timestamp(e)]
        sub_evt = [x for x in rm_evt._sizing_log
                   if x["date"] is not None and pd.Timestamp(s) <= x["date"] <= pd.Timestamp(e)]
        br_evt = (sum(1 for x in sub_evt if x.get("active") == "by_risk") / len(sub_evt)) \
            if sub_evt else float("nan")
        br_base = (sum(1 for x in sub_base if x.get("active") == "by_risk") / len(sub_base)) \
            if sub_base else float("nan")
        gate_per_window[label] = {
            "n_compras_evt_ventana": len(sub_evt),
            "pct_by_risk_activo_evt": br_evt,
            "pct_by_risk_activo_base": br_base,
            "gate_ok": bool(np.isfinite(br_evt) and br_evt >= ACTIVATION_MIN),
        }
        dsr = mv.get("deflated_sharpe", float("nan"))
        ok_trades = len(trv) >= TRADE_FLOOR
        ok_dsr = bool(ok_trades and np.isfinite(dsr) and dsr >= DSR_THRESHOLD)
        results[label] = {"base": mb, "evt": mv, "n_base": len(trb), "n_evt": len(trv)}
        verdict_rows.append((label, len(trb), len(trv), dsr, ok_trades, ok_dsr))
        log(f"\n--- {label} (BASE n={len(trb)}, EVT n={len(trv)}) ---")
        for c in cols:
            b, v = mb.get(c, float("nan")), mv.get(c, float("nan"))
            log(f"    {c:18s} {b:12.4f} {v:12.4f}")
        log(f"    GATE F7 ventana: compras_EVT={len(sub_evt)} pct_by_risk={br_evt}")

    # ---------- GATE DE ACTIVACIÓN F7 ----------
    gate_ok_windows = [w for w, g in gate_per_window.items() if g["gate_ok"]]
    interpretable = len(gate_ok_windows) >= 2
    log("\n" + "=" * 76)
    log("GATE DE ACTIVACIÓN F7 (pre-registrado §45): ventanas con pct_by_risk>=%s: %s"
        % (f"{ACTIVATION_MIN:.0%}", gate_ok_windows))
    log("Corrida INTERPRETABLE: %s" % ("SÍ" if interpretable else "NO"))

    if interpretable:
        passed = [ok_dsr for (_l, _nb, _nv, _d, _t, ok_dsr) in verdict_rows]
        for (label, nb, nv, dsr, ok_trades, ok_dsr) in verdict_rows:
            log("  %s: n_EVT=%d DSR=%.4f vs th=%.5f -> %s%s"
                % (label, nv, dsr, DSR_THRESHOLD,
                   "PASA" if ok_dsr else "no pasa",
                   "" if ok_trades else " (no evaluable: < piso trades)"))
        global_verdict = "CUMPLE" if sum(passed) >= 2 else "NO_CUMPLE"
        log("\nVEREDICTO MECÁNICO §45: %s (%d/3 ventanas)" % (global_verdict, sum(passed)))
        ledger_status = "REGISTRA"
    else:
        global_verdict = None
        log("\nVEREDICTO: NO INTERPRETABLE — F7 falló. NO se registra en "
            "trial_registry (no consume slot motor_signal), intento inválido "
            "documentado (mismo tratamiento que #15 original).")
        ledger_status = "NO_REGISTRA"

    heartbeat_stop.set()

    pd.DataFrame(res_evt["trades"]).to_parquet(out_path.replace(".txt", "_evt_trades.parquet"))
    pd.DataFrame(res_evt["equity_curve"]).to_parquet(out_path.replace(".txt", "_evt_equity.parquet"))
    pd.DataFrame(res_base["trades"]).to_parquet(out_path.replace(".txt", "_base_trades.parquet"))

    payload = {
        "trial_id": "trial_evt_stops_v2",
        "status": "EJECUTADO",
        "pre_registro": "PLAN_MEJORA_MATEMATICA.md §45",
        "familia": "motor_signal",
        "ledger_runtime": {"consumido_antes": N_FAM_CONSUMED,
                           "n_trial": N_TRIALS_DSR,
                           "dsr_threshold": DSR_THRESHOLD},
        "dial": {"risk_per_trade_arm": RISK_PER_TRADE_ARM,
                 "kelly": "desactivado simétrico",
                 "max_position_pct": 0.10},
        "checks_fidelidad": checks,
        "activacion": {"base": act_base, "evt": act_evt,
                       "por_ventana": gate_per_window,
                       "gate_f7_ok": interpretable,
                       "ledger_status": ledger_status},
        "resultados_por_ventana": results,
        "veredicto_global": global_verdict,
        "timestamp": ts,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=float)
    log(f"\nOut: {out_path}")
    print("ARTIFACT:%s" % out_path)
    print("LEDGER_STATUS:%s" % ledger_status)
    print("VEREDICTO_GLOBAL:%s" % (global_verdict or "NO_INTERPRETABLE_F7"))
    print("DSR_THRESHOLD:%.5f" % DSR_THRESHOLD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
