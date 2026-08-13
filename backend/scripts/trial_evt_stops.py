"""
TRIAL #15 (PLAN §20) — Stops EVT walk-forward en el sizing del motor (2026-08-13).
PRE-REGISTRADO antes de correr (ver §20 en el plan).

Cambio vs baseline: en compute_position_size, stop_distance pasa de
max(2xATR, price*position_stop) a max(VaR_GPD(99%)_vigente x sigma_EWMA_dia,
price*position_stop). Todo lo demas del risk manager INTACTO (variante minima).

Anti-lookahead (correccion del usuario, 2026-08-13): los parametros EVT se
recalibran walk-forward cada 63 dias habiles con ventana movil de 756 dias
habiles sobre retornos estandarizados EWMA (lambda=0.94), con data desde
2015-01-01: toda decision usada en las ventanas W1-W3 tiene parametros con
historia <= fecha de decision, nunca con datos futuros.

Ventanas: W1 2020-2021, W2 2022-2023, W3 2024-2026-08-04. Piso: >= 30 trades.
Criterio: DSR OOS >= 0.90 en >= 2/3 ventanas. N_TRIALS = 19 (17 historico + 1
trial #14 + 1 este; Fase 0.6 re-test sin slot; §18/§19 sin slot).
"""
import datetime
import os

import numpy as np
import pandas as pd
from app.core.adaptive_risk import AdaptiveRiskManager
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from scipy.stats import genpareto
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
DATA_START = "2015-01-01"
OP_START = "2019-01-01"
END = "2026-08-04"
N_TRIALS = 19
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


def ewma_vol_daily(r: pd.Series, warmup: int = 60) -> pd.Series:
    r2 = r.to_numpy()
    v = float(np.var(r2[:warmup], ddof=1)) if len(r2) > warmup else float(np.var(r2, ddof=1))
    out = np.empty(len(r2))
    v = 0.0 if not np.isfinite(v) else v
    for t in range(len(r2)):
        if t > 0:
            v = LAMBDA * v + (1 - LAMBDA) * r2[t - 1]
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


class EVTRiskManager(AdaptiveRiskManager):
    """Risk manager con stop_distance EVT walk-forward por activo."""

    def __init__(self, capital: float, price_data: dict):
        super().__init__(capital)
        self._var_table: dict = {}
        self._current_date = None
        self._n_evt_buys = 0
        self._batches = []
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
        """Multiplicador VaR_GPD vigente; None si el activo no esta calibrado.
        side='left' -> recalibracion ESTRICTAMENTE anterior a la fecha de compra
        (anti-lookahead; si la compra cae el dia de una recalibracion, se usa la
        anterior). Todas las fechas se normalizan a np.datetime64: searchsorted
        de numpy 2.x falla con listas python de datetime64 contra Timestamp."""
        rec_dates = self._var_table.get(symbol)
        if rec_dates is None:
            return None
        vars_ = self._var_table[symbol + "__var"]
        as_dt = np.datetime64(pd.Timestamp(price_date))
        idx = np.searchsorted(rec_dates, as_dt, side="left") - 1
        if idx < 0:
            return None
        return vars_[idx]

    def _sig_at_date(self, symbol: str, price_date) -> float:
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
        if symbol is None:
            return super().compute_position_size(equity, price, atr, win_prob,
                                                 payoff_ratio, fractional_kelly)
        var_mult = self._var_mult(symbol, self._current_date)
        sig_today = self._sig_at_date(symbol, self._current_date)
        if var_mult is None or sig_today is None:
            return super().compute_position_size(equity, price, atr, win_prob,
                                                 payoff_ratio, fractional_kelly, symbol)
        self._n_evt_buys += 1
        rec_dates = self._var_table[symbol]
        as_dt = np.datetime64(self._current_date)
        idx = np.searchsorted(rec_dates, as_dt, side="left") - 1
        assert idx >= 0, f"EVT sin recalibracion previa para {symbol} el {self._current_date}"
        assert rec_dates[idx] < as_dt, (
            f"LOOKAHEAD EVT: recalibracion {rec_dates[idx]} no es anterior a compra {self._current_date}"
        )
        thresholds = self.get_thresholds()
        stop_distance = max(var_mult * sig_today, price * thresholds["position_stop"])
        shares_by_risk = (equity * self.RISK_PER_TRADE) / stop_distance
        max_shares = (equity * self.MAX_POSITION_PCT) / price
        if win_prob is not None and payoff_ratio is not None:
            p = min(max(win_prob, 0.01), 0.99)
            b = max(payoff_ratio, 0.01)
            kelly = max(0.0, (p * b - (1 - p)) / b) * fractional_kelly
            if kelly > 0:
                kelly_shares = (equity * kelly) / price
                return int(min(kelly_shares, shares_by_risk, max_shares))
        return int(min(shares_by_risk, max_shares))


class EVTEngine(BacktestEngine):
    def __init__(self, initial_capital: float = 25000.0, price_data: dict = None):
        super().__init__(initial_capital)
        self._evt_price_data = price_data
        self._used_rm = None

    def _make_risk_manager(self):
        rm = EVTRiskManager(self.initial_capital, self._evt_price_data)
        self._used_rm = rm
        return rm


def period_metrics(equity_curve, trades, s, e, engine, n_trials):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=n_trials), tr


def main():
    out_path = os.path.join("data", "cache",
                            f"trial15_evt_stops_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("TRIAL #15 (PLAN §20) — STOPS EVT WALK-FORWARD EN EL SIZING (PRE-REGISTRADO)")
    log(f"Universo: {len(SYMBOLS)} simbolos | data {DATA_START} -> {END} | operacion {OP_START} -> {END}")
    log("Cambio: stop_distance = max(VaR_GPD(99%)_vigente x sigma_EWMA_dia, price*position_stop)")
    log("vs baseline max(2xATR, price*position_stop). Resto del risk manager INTACTO.")
    log(f"Walk-forward: recalibracion cada {BATCH_DAYS}d habiles, ventana movil {CAL_WINDOW_DAYS}d, "
        f"EWMA lambda={LAMBDA}, u=p{U_QUANTILE:.0%}, VaR p{VAR_LEVEL:.0%} | excesos<{MIN_EXCESS} -> cuantil empirico")
    log(f"Ventanas: {', '.join(w[0] for w in WINDOWS)} | piso trades/ventana: {TRADE_FLOOR}")
    log(f"Criterio: DSR OOS >= 0.90 en >= 2/3 ventanas | N_TRIALS={N_TRIALS} (17 historico +1 #14 +1 este)")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, DATA_START, END)
    price_data = load_universe(SYMBOLS, DATA_START, END)
    log(f"precios cargados: {len(price_data)}/{len(SYMBOLS)} simbolos ({DATA_START} -> {END})")

    evt_rm = EVTRiskManager(25000.0, price_data)
    n_sym_cal = sum(1 for s in SYMBOLS if s in evt_rm._var_table)
    n_batches = len(evt_rm._batches)
    log(f"EVT calibrado walk-forward: {n_sym_cal}/{len(SYMBOLS)} simbolos | {n_batches} fechas de recalibracion "
        f"(esperadas ~{(2900-756)//63}) | fallback a cuantil empirico solo si una ventana tiene <{MIN_EXCESS} excesos "
        f"(esperados ~38/ventana)")

    log("\nCorriendo baseline (BacktestEngine estandar, misma data)...")
    res_base = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(OP_START), pd.Timestamp(END)
    )
    log("Corriendo EVT (EVTEngine con EVTRiskManager walk-forward)...")
    evt_engine = EVTEngine(initial_capital=25000, price_data=price_data)
    res_evt = evt_engine.run(
        price_data, market_data, pd.Timestamp(OP_START), pd.Timestamp(END)
    )
    n_buys = evt_engine._used_rm._n_evt_buys if evt_engine._used_rm is not None else 0
    log(f"Compras EVT dimensionadas con VaR-GPD walk-forward: {n_buys} (assert anti-lookahead "
        f"activo en todas: recalibracion estrictamente anterior a la compra)")

    pd.DataFrame(res_evt["trades"]).to_parquet(out_path.replace(".txt", "_evt_trades.parquet"))
    pd.DataFrame(res_evt["equity_curve"]).to_parquet(out_path.replace(".txt", "_evt_equity.parquet"))

    engine = BacktestEngine(initial_capital=25000)
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    for label, s, e in WINDOWS:
        mb, trb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine, N_TRIALS)
        mv, trv = period_metrics(res_evt["equity_curve"], res_evt["trades"], s, e, engine, N_TRIALS)
        log(f"\n--- {label} (baseline n={len(trb)}, EVT n={len(trv)}) ---")
        for c in cols:
            b, v = mb.get(c, float("nan")), mv.get(c, float("nan"))
            log(f"    {c:18s} {b:12.4f} {v:12.4f}")

    log("\n--- VEREDICTO vs CRITERIO (§20) ---")
    passed = []
    for label, s, e in WINDOWS:
        _, trv = period_metrics(res_evt["equity_curve"], res_evt["trades"], s, e, engine, N_TRIALS)
        ok_trades = len(trv) >= TRADE_FLOOR
        mv, _ = period_metrics(res_evt["equity_curve"], res_evt["trades"], s, e, engine, N_TRIALS)
        dsr = mv.get("deflated_sharpe", float("nan"))
        ok_dsr = ok_trades and dsr >= 0.90
        passed.append(ok_dsr)
        log(f"  {label:14s} n={len(trv):3d} DSR={dsr:.4f} {'PASA' if ok_dsr else 'no pasa'}"
            f"{'' if ok_trades else ' (no evaluable: < piso de trades)'}")
    log(f"\n  Ventanas que pasan: {sum(passed)}/3 -> criterio: {'CUMPLE' if sum(passed) >= 2 else 'NO CUMPLE'}")
    if sum(passed) >= 2:
        log("  => CUMPLE: el sizing EVT mejora el sistema -> evaluar integracion con el "
            "gate 'mejora VaR/ES real' del plan (drawdown/cola realizada EVT vs baseline).")
    else:
        log("  => NO CUMPLE: el sizing EVT no supera al baseline -> no se integra; Fase 1 "
            "queda cerrada con §19 (diagnostico) + §20 (trial) como evidencia.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
