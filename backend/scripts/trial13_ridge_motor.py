"""
TRIAL #13 (PLAN §13) — Ridge_3f como score del motor, universo 50 símbolos.

Cambio vs trial #10/Phase A: el score de generate_signal deja de ser
blend |IC| + BMA y pasa a ser la predicción walk-forward de ridge_3f
(momentum_score + rsi_score + macro_composite, RidgeCV estandarizado).
TODO lo demás es idéntico: gates duros, stops, TP, salidas, régimen HMM,
costos, position sizing Kelly con calibrador Platt (que se re-entrena solo
sobre los nuevos scores vía _build_calibration_dataset).

Criterio: el ORIGINAL de §9.4 — DSR OOS >= 0.90 en >= 2/3 ventanas
evaluables. N_TRIALS = 17. Ventanas W1/W2/W3 §9.4. Piso: >= 30 trades.
El trial corre SIN sentiment_data: §11.4 define ridge como score de
ranking/entrada (el g2 de sentimiento quedaría por encima del score en
rank_signals y contaminaría la atribución).

Entrenamiento del ridge (sin lookahead, §13.3):
- Panel diario (stride 1) por símbolo x fecha: momentum_score y rsi_score
  de compute_factor_frame (mismo código del motor), macro_composite de
  _macro_signals (causal, datos <= fecha), eligible, target_date.
- Train: SOLO filas eligible con target realizado al refit (target_date
  <= fecha de refit — el retorno a 20d hábiles se conoce 20d después).
- Refit cada 63 días calendario (CALIBRATOR_REFIT_STRIDE_DAYS), ventana
  expansiva. RidgeCV(alphas=logspace(-4,2,30)) + StandardScaler fit solo
  en train. Min filas de train: 50.
- Predicción para fechas [refit, siguiente_refit): modelo del refit.
- Sin modelo o NaN -> sin señal (misma semántica que el warmup del motor).

Si no pasa el criterio -> revertir = borrar este script y archivar la
evidencia (patrón trial #11).
"""
import datetime
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from app.core.backtest_engine import (
    BacktestEngine, CALIBRATION_HORIZON_DAYS, CALIBRATOR_REFIT_STRIDE_DAYS,
)
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.market_sentiment import build_sentiment_frame
from app.core.predictive_engine import PredictiveEngine
from app.core.probabilistic_engine import BayesianOnlineUpdater
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.signal_engine import SignalEngine
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
MACRO_TICKERS = {
    "DXY": "DX-Y.NYB", "gold": "GC=F", "silver": "SI=F",
    "TLT": "TLT", "SPY": "SPY", "oil": "CL=F", "copper": "HG=F",
}
START = "2019-01-01"
END = "2026-08-04"
N_TRIALS = 17
WINDOWS = [
    ("W1 2020-2021", "2020-01-01", "2021-12-31"),
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]
TRADE_FLOOR = 30
RIDGE_ALPHAS = np.logspace(-4, 2, 30)
MIN_TRAIN_ROWS = 50

FEATURES = ["momentum_score", "rsi_score", "macro_composite"]


class RidgeSignalEngine(SignalEngine):
    """SignalEngine cuyo score es la predicción walk-forward de ridge_3f.

    Los gates duros, stops, TP y la estructura de la señal son IDENTICOS
    a la clase base; solo cambia qué se usa como score y su umbral.
    """

    def __init__(self, regime_classifier, bayesian_updater=None, ridge_scores=None):
        super().__init__(regime_classifier, bayesian_updater=bayesian_updater)
        self.ridge_scores = ridge_scores or {}

    def generate_signal(self, stock_data, symbol, regime_state):
        if len(stock_data) < 200 or regime_state == 3:
            return None

        stock_data = calculate_all_indicators(stock_data)
        if len(stock_data) == 0:
            return None
        latest = stock_data.iloc[-1]
        date = stock_data.index[-1]
        scores = self._factor_scores(stock_data)

        # Gates duros — idénticos a la clase base.
        if not (latest.close > latest.ema50 > latest.ema200):
            return None
        if latest.get("adx14", 0) < 20:
            return None
        if not (40 < latest.get("rsi14", 50) < 75):
            return None
        if latest.get("volume_ratio", 1) < 1.0:
            return None

        # Score = predicción ridge_3f (reemplaza blend |IC| + BMA).
        series = self.ridge_scores.get(symbol)
        if series is None or date not in series.index:
            return None
        score = float(series.loc[date])
        if not np.isfinite(score) or score <= 0.0:
            return None

        atr_v = latest.atr14
        entry = latest.close
        stop_loss = entry - 2.0 * atr_v
        take_profit = entry + 4.0 * atr_v
        risk = entry - stop_loss
        payoff_ratio = (take_profit - entry) / risk if risk > 0 else 0.0
        return {
            "symbol": symbol,
            "date": date,
            "signal_type": "BUY",
            "score": float(score),
            "entry_price": float(entry),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "payoff_ratio": float(payoff_ratio),
            "regime_state": regime_state,
            "factors": scores,
            "atr": float(atr_v),
            "indicators": {
                "close": float(latest.close),
                "ema50": float(latest.ema50),
                "ema200": float(latest.ema200),
                "adx14": float(latest.get("adx14", np.nan)),
                "rsi14": float(latest.get("rsi14", np.nan)),
                "volume_ratio": float(latest.get("volume_ratio", np.nan)),
            },
        }


class RidgeMotorEngine(BacktestEngine):
    """BacktestEngine con el SignalEngine de ridge inyectado."""

    def __init__(self, initial_capital=25000.0, ridge_scores=None):
        self.initial_capital = initial_capital
        self.regime_classifier = GlobalRegimeClassifier()
        self.bayesian_updater = BayesianOnlineUpdater()
        self.signal_engine = RidgeSignalEngine(
            self.regime_classifier, bayesian_updater=self.bayesian_updater, ridge_scores=ridge_scores
        )


def build_daily_panel(price_data, market_data, log):
    """Panel diario (stride 1) de features para el ridge.

    momentum_score/rsi_score/eligible salen de compute_factor_frame (el
    MISMO código que usa el motor); macro_composite es causal (solo datos
    <= fecha) y se cachea por fecha (no depende del símbolo). target_date
    es la fecha en que el retorno a 20d hábiles se conoce; fwd_return es
    ese retorno (NaN en la cola, donde todavía no existe).
    """
    macro_data = {k: market_data.get(v) for k, v in MACRO_TICKERS.items()}
    macro_data = {k: v for k, v in macro_data.items() if v is not None}
    engine = PredictiveEngine()
    signal_engine = SignalEngine(GlobalRegimeClassifier())
    macro_cache = {}

    frames = {}
    for symbol, df in price_data.items():
        if len(df) < 220 + CALIBRATION_HORIZON_DAYS:
            continue
        ind = calculate_all_indicators(df)
        frames[symbol] = signal_engine.compute_factor_frame(ind)

    rows = []
    for symbol, frame in frames.items():
        close = frame["close"]
        for i, date in enumerate(frame.index):
            if date not in macro_cache:
                sliced = {k: v[v.index <= date] for k, v in macro_data.items()}
                _, composite = engine._macro_signals(sliced)
                macro_cache[date] = float(composite)
            if i + CALIBRATION_HORIZON_DAYS < len(frame):
                target_date = frame.index[i + CALIBRATION_HORIZON_DAYS]
                fwd_return = close.iloc[i + CALIBRATION_HORIZON_DAYS] / close.iloc[i] - 1.0
            else:
                target_date, fwd_return = pd.NaT, np.nan
            rows.append({
                "date": date, "symbol": symbol,
                "momentum_score": float(frame["momentum"].iloc[i]),
                "rsi_score": float(frame["rsi"].iloc[i]),
                "macro_composite": macro_cache[date],
                "eligible": bool(frame["eligible"].iloc[i]),
                "target_date": target_date,
                "fwd_return": float(fwd_return),
            })

    panel = pd.DataFrame(rows)
    log(f"panel diario: {len(panel)} filas, {panel['symbol'].nunique()} símbolos, "
        f"{panel['date'].nunique()} fechas, eligible={int(panel['eligible'].sum())}")
    return panel


def walk_forward_ridge_scores(panel, log):
    """Entrena ridge_3f con refit cada CALIBRATOR_REFIT_STRIDE_DAYS (63d),
    ventana expansiva, y devuelve {symbol: pd.Series(predicción, index)}.

    Sin lookahead: en el refit de fecha R el train usa SOLO filas con
    target_date <= R (el retorno a 20d hábiles no se conoce antes). Las
    fechas [R, siguiente_refit) se predicen con el modelo fit en R. Filas
    sin modelo -> NaN (sin señal, semántica de warmup).
    """
    panel = panel.sort_values("date").reset_index(drop=True)
    all_dates = sorted(panel["date"].unique())

    refits = [all_dates[0]]
    for d in all_dates[1:]:
        if (d - refits[-1]).days >= CALIBRATOR_REFIT_STRIDE_DAYS:
            refits.append(d)

    train = panel[panel["eligible"] & panel["target_date"].notna()].copy()
    train["target_date"] = pd.to_datetime(train["target_date"])

    pred_buf = {s: [] for s in sorted(panel["symbol"].unique())}
    model, scaler, n_refits = None, None, 0

    for i, refit_date in enumerate(refits):
        # Refit en refit_date: ventana expansiva con target realizado.
        # El modelo solo ve filas con target_date <= refit_date (targets
        # realizados a lo sumo ese día) -> predecir fechas >= refit_date
        # con este modelo no tiene lookahead.
        usable = train[train["target_date"] <= refit_date]
        if len(usable) >= MIN_TRAIN_ROWS:
            X_tr = usable[FEATURES].values
            y_tr = usable["fwd_return"].values
            scaler = StandardScaler().fit(X_tr)
            model = RidgeCV(alphas=RIDGE_ALPHAS).fit(scaler.transform(X_tr), y_tr)
            n_refits += 1

        # Predicción del segmento [refit_date, seg_end] con el modelo de
        # este refit (si existe).
        seg_end = refits[i + 1] - pd.Timedelta(days=1) if i + 1 < len(refits) else all_dates[-1]
        if model is not None:
            seg = panel[(panel["date"] >= refit_date) & (panel["date"] <= seg_end)]
            if len(seg):
                X = scaler.transform(seg[FEATURES].values)
                for dt, sym, val in zip(seg["date"], seg["symbol"], model.predict(X)):
                    pred_buf[sym].append((dt, float(val)))

    scores = {}
    for sym, buf in pred_buf.items():
        if buf:
            idx = pd.DatetimeIndex([d for d, _ in buf])
            scores[sym] = pd.Series([v for _, v in buf], index=idx).sort_index()
    log(f"refits ridge: {n_refits} | símbolos con score: {len(scores)}")
    return scores


def period_metrics(equity_curve, trades, s, e, engine, n_trials):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=n_trials), tr


def main():
    out_path = os.path.join("data", "cache", f"trial13_ridge_motor_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg, flush=True)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("TRIAL #13 (PLAN §13) — Ridge_3f como score del motor")
    log(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END} | costos 0.15%/lado")
    log(f"Cambio: score = predicción ridge_3f walk-forward (refit {CALIBRATOR_REFIT_STRIDE_DAYS}d, "
        f"expansivo, StandardScaler fit en train, gate ridge_pred > 0)")
    log(f"Ventanas: {', '.join(w[0] for w in WINDOWS)} | piso trades/ventana: {TRADE_FLOOR}")
    log(f"Criterio: DSR OOS >= 0.90 en >= 2/3 ventanas evaluables | N_TRIALS={N_TRIALS}")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)
    log(f"precios cargados: {len(price_data)} símbolos")

    trading_dates = price_data["SPY"].index
    sentiment = build_sentiment_frame(trading_dates)
    sent_map = {ts: float(v) for ts, v in sentiment["aaii_bullbear_spread"].items() if pd.notna(v)}

    log("\nConstruyendo panel diario de features...")
    panel = build_daily_panel(price_data, market_data, log)

    log("\nEntrenando ridge walk-forward...")
    ridge_scores = walk_forward_ridge_scores(panel, log)

    log("\nCorriendo baseline (50 símbolos, sin V1)...")
    res_base = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END)
    )

    log("Corriendo V1-ranking (50 símbolos, G2 con AAII)...")
    res_v1 = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        sentiment_data=sent_map,
    )

    log("Corriendo ridge_3f como score (EL trial)...")
    res_ridge = RidgeMotorEngine(initial_capital=25000, ridge_scores=ridge_scores).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END)
    )

    pd.DataFrame(res_ridge["trades"]).to_parquet(out_path.replace(".txt", "_trades.parquet"))
    pd.DataFrame(res_ridge["risk_events"]).to_parquet(out_path.replace(".txt", "_events.parquet"))
    pd.DataFrame(res_ridge["equity_curve"]).to_parquet(out_path.replace(".txt", "_equity.parquet"))

    engine = BacktestEngine(initial_capital=25000)
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    for label, s, e in WINDOWS:
        mb, trb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine, N_TRIALS)
        mv, trv = period_metrics(res_v1["equity_curve"], res_v1["trades"], s, e, engine, N_TRIALS)
        mr, trr = period_metrics(res_ridge["equity_curve"], res_ridge["trades"], s, e, engine, N_TRIALS)
        log(f"\n--- {label} (baseline n={len(trb)}, V1 n={len(trv)}, ridge n={len(trr)}) ---")
        for c in cols:
            b, v, r = mb.get(c, float("nan")), mv.get(c, float("nan")), mr.get(c, float("nan"))
            log(f"    {c:18s} {b:12.4f} {v:12.4f} {r:12.4f}")

    log("\n--- TRADES POR VENTANA (ridge) ---")
    for label, s, e in WINDOWS:
        oos = [t for t in res_ridge["trades"] if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
        wins = sum(1 for t in oos if t["pnl"] > 0)
        evaluable = len(oos) >= TRADE_FLOOR
        log(f"  {label:14s} trades={len(oos):3d} wins={wins:3d} win_rate={wins / len(oos) if oos else float('nan'):.3f} evaluable={evaluable}")

    log("\n--- MONTE CARLO (bootstrap, ridge) ---")
    boot = res_ridge["monte_carlo"].get("bootstrap", {})
    log(f"  mean={boot.get('mean', float('nan')):+.1f} p5={boot.get('p5', float('nan')):+.1f} "
        f"p95={boot.get('p95', float('nan')):+.1f} prob_loss={boot.get('prob_loss', float('nan')):.3f}")

    log("\n--- VEREDICTO vs CRITERIO (§9.4) ---")
    passed = []
    for label, s, e in WINDOWS:
        mr, trr = period_metrics(res_ridge["equity_curve"], res_ridge["trades"], s, e, engine, N_TRIALS)
        ok_trades = len(trr) >= TRADE_FLOOR
        dsr = mr.get("deflated_sharpe", float("nan"))
        ok_dsr = ok_trades and dsr >= 0.90
        passed.append(ok_dsr)
        log(f"  {label:14s} n={len(trr):3d} DSR={dsr:.4f} {'PASA' if ok_dsr else 'no pasa'}"
            f"{'' if ok_trades else ' (no evaluable: < piso de trades)'}")
    log(f"\n  Ventanas que pasan: {sum(passed)}/3 -> criterio: {'CUMPLE' if sum(passed) >= 2 else 'NO CUMPLE'}")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
