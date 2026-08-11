"""
PLAN §11 Fase 0 — Panel de factores unificado (proyecto combinación multivariada).

Construye UNA vez el panel diario que consumen los diagnósticos de §11:
- Por símbolo x fecha (stride semanal, igual que el resto de los diags):
    momentum_score, rsi_score     (de compute_factor_frame, el MISMO código del motor)
    sentiment_v1                  (AAII spread, anti-lookahead de build_sentiment_frame)
    macro_composite               (de _macro_signals, mismo código de producción)
    regime                        (estado HMM real del día, refit trimestral
                                   walk-forward expansivo — IGUAL que el backtest)
    fwd_return_20d                (horizonte CALIBRATION_HORIZON_DAYS del motor)
    eligible                      (máscara del gate: trend+ADX+RSI+vol)
- Solo días eligible son operables: el IC se mide sobre esa población
  (mismo criterio que validate_signal_quality).

Salida: data/cache/factor_panel_<ts>.parquet + resumen por consola.
Este script NO mide nada: solo materializa el panel para 1a/1b/2.
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd

from app.core.backtest_engine import CALIBRATION_HORIZON_DAYS
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.market_sentiment import build_sentiment_frame
from app.core.predictive_engine import PredictiveEngine
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.signal_engine import SignalEngine
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
START = "2019-01-01"
END = "2026-08-04"
STRIDE_DAYS = 5          # semanal, mismo que los diags de IC
REGIME_REFIT_STRIDE_DAYS = 63  # trimestral, mismo que backtest_engine

MACRO_TICKERS = {
    "DXY": "DX-Y.NYB", "gold": "GC=F", "silver": "SI=F",
    "TLT": "TLT", "SPY": "SPY", "oil": "CL=F", "copper": "HG=F",
}


def main():
    out_path = os.path.join(
        "data", "cache", f"factor_panel_{datetime.datetime.now():%Y%m%d_%H%M%S}.parquet"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    print("Cargando precios...", flush=True)
    price_data = load_universe(SYMBOLS, START, END)
    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    # FIX auditoría (2026-08-11): MARKET_TICKERS NO incluye DXY/gold/oil,
    # así que el composite macro del panel (y del motor) solo recibía
    # SPY+TLT — las reglas 1 (DXY/Oro), 6 (Petróleo) nunca entraban.
    # Cargar los macro faltantes para el panel limpio de Fase -1/0.5.
    macro_extra = load_universe(["DX-Y.NYB", "GC=F", "CL=F"], "2015-01-01", END)
    market_data = {**market_data, **macro_extra}
    print(f"  {len(price_data)} símbolos, {len(market_data)} tickers de mercado", flush=True)

    trading_dates = price_data["SPY"].index
    print("Construyendo frame de sentimiento (AAII, anti-lookahead)...", flush=True)
    sentiment_frame = build_sentiment_frame(trading_dates)
    sent_map = {
        ts: float(v) for ts, v in sentiment_frame["aaii_bullbear_spread"].items() if pd.notna(v)
    }
    print(f"  AAII en {len(sent_map)}/{len(trading_dates)} días", flush=True)

    macro_data = {
        k: market_data.get(v) for k, v in MACRO_TICKERS.items()
    }
    macro_data = {k: v for k, v in macro_data.items() if v is not None}

    engine = PredictiveEngine()
    regime_clf = GlobalRegimeClassifier()
    signal_engine = SignalEngine(regime_clf)
    regime_clf.fit(market_data)

    print("Pre-computando indicadores por símbolo (una sola vez)...", flush=True)
    factor_frames = {}
    for symbol, df in price_data.items():
        if len(df) > 220:
            factor_frames[symbol] = signal_engine.compute_factor_frame(
                calculate_all_indicators(df)
            )
    print(f"  {len(factor_frames)} símbolos con indicadores", flush=True)

    dates = trading_dates[(trading_dates >= pd.Timestamp(START)) &
                          (trading_dates <= pd.Timestamp(END))]
    stride_dates = dates[::STRIDE_DAYS]

    rows = []
    last_regime_refit = pd.Timestamp(START)

    print(f"Armando panel sobre {len(stride_dates)} fechas (stride {STRIDE_DAYS}d)...", flush=True)
    for date in stride_dates:
        if (date - last_regime_refit).days >= REGIME_REFIT_STRIDE_DAYS:
            try:
                regime_clf.fit({s: df[df.index < date] for s, df in market_data.items()})
            except ValueError:
                pass  # ventana insuficiente -> seguir con modelo anterior
            last_regime_refit = date
        # FIX auditoría §3.1 (2026-08-11): antes se pasaba market_data
        # COMPLETO (hasta END) -> cada fila recibía el régimen del último
        # día de toda la serie (lookahead). Cortar en 'date' igual que el
        # refit de arriba y que el backtest real (backtest_engine.py).
        regime_state = int(regime_clf.predict_current_regime(
            {s: df[df.index <= date] for s, df in market_data.items()}
        )["state"])

        sliced_macro = {k: df[df.index <= date] for k, df in macro_data.items()}
        _, macro_composite = engine._macro_signals(sliced_macro)
        # FIX auditoría §4.3 (2026-08-11): el ridge DEBE alimentarse de las
        # 3 componentes macro CRUDAS como features separadas, no del
        # composite re-ponderado (pesos |IC| tuneados in-sample, §3.2/§3.3).
        # Retornos crudos, sin umbrales internos de cada regla. Se calculan
        # sobre sliced_macro (<= date) — nunca sobre la serie completa.
        def _ret(ticker, window, default=np.nan):
            df = sliced_macro.get(ticker)
            if df is None or len(df) <= window:
                return default
            return float(df["close"].pct_change(window).iloc[-1] * 100)

        macro_raw = {
            # Risk Switch (regla 1): DXY y Oro por separado, sin el umbral
            # ±1% de la regla ni el weight 0.2588
            "dxy_ret_20d": _ret("DXY", 20),
            "gold_ret_20d": _ret("gold", 20),
            # S&P momentum 50d (regla 5), crudo, sin invertir ni normalizar
            "spy_ret_50d": _ret("SPY", 50),
            # Petróleo 20d (regla 6), crudo, sin umbral ±10%
            "oil_ret_20d": _ret("oil", 20),
        }
        sentiment_v1 = sent_map.get(date, np.nan)

        for symbol, frame in factor_frames.items():
            if date not in frame.index:
                continue
            pos = frame.index.get_loc(date)
            close = frame["close"].iloc[pos]
            if pos + CALIBRATION_HORIZON_DAYS >= len(frame):
                continue
            future = frame["close"].iloc[pos + CALIBRATION_HORIZON_DAYS]

            rows.append({
                "date": date,
                "symbol": symbol,
                "momentum_score": frame["momentum"].iloc[pos],
                "rsi_score": frame["rsi"].iloc[pos],
                "trend_score": frame["trend"].iloc[pos],
                "adx_score": frame["adx"].iloc[pos],
                "sentiment_v1": sentiment_v1,
                "macro_composite": macro_composite,
                **macro_raw,
                "regime": regime_state,
                "fwd_return_20d": future / close - 1.0,
                "eligible": bool(frame["eligible"].iloc[pos]),
            })

    panel = pd.DataFrame(rows)
    panel.to_parquet(out_path)

    n_total = len(panel)
    n_eligible = int(panel["eligible"].sum())
    print("\n=== PANEL GENERADO ===")
    print(f"  filas totales: {n_total}")
    print(f"  filas eligible (operables, IC se mide aquí): {n_eligible} ({n_eligible / n_total:.1%})")
    print(f"  símbolos: {panel['symbol'].nunique()} | fechas: {panel['date'].nunique()}")
    print(f"  régimenes representados: {sorted(panel['regime'].unique())}")
    print(f"  NaN sentiment_v1: {int(panel['sentiment_v1'].isna().sum())} "
          f"| NaN macro: {int(panel['macro_composite'].isna().sum())}")
    print(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
