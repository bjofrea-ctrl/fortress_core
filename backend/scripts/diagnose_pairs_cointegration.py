"""
PLAN §12 Fase 4a — Barrido de cointegración entre pares del universo 50.

Diagnóstico: ¿cuántos pares del universo mantienen una relación de
cointegración ESTABLE en el tiempo? Para cada par, adfuller sobre el spread
del log-precios en ventana 252d, muestreado trimestralmente 2019→2026.

Regla de estabilidad pre-registrada (§12.2.1): un par es candidato si es
cointegrado (estadística adfuller significativa al 5%) en >= 60% de las
ventanas muestreadas. La lista resultante se congela: el backtest 4b usa
solo estimaciones walk-forward, nunca esta lista como información futura
(la lista solo define QUÉ pares se monitorizan).

Salida: data/cache/pairs_coint_<ts>.txt + .parquet con el detalle por par.
"""
import datetime
import itertools
import os
import sys

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
WINDOW_DAYS = 252
SAMPLE_STRIDE = 63  # trimestral
MIN_STABLE_PCT = 0.60  # % de ventanas donde el par es cointegrado


def spread_stationary(x: np.ndarray, y: np.ndarray, p: float = 0.05) -> bool:
    """Regresión OLS spread = log(x) - beta*log(y) con beta = cov/var (OLS),
    adfuller sobre el residuo."""
    lx, ly = np.log(x), np.log(y)
    beta = np.cov(lx, ly)[0, 1] / np.var(ly)
    spread = lx - beta * ly
    stat, pval, *_ = adfuller(spread, autolag="AIC")
    return bool(pval < p)


def main():
    out_path = os.path.join("data", "cache", f"pairs_coint_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    parquet_path = out_path.replace(".txt", ".parquet")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    print("Cargando precios...", flush=True)
    price_data = load_universe(SYMBOLS, START, END)
    closes = pd.DataFrame({s: df["close"] for s, df in price_data.items() if len(df) > WINDOW_DAYS + 100})
    closes = closes.dropna(how="any")
    symbols = list(closes.columns)
    print(f"  {len(symbols)} símbolos con serie completa", flush=True)

    sample_dates = closes.index[::SAMPLE_STRIDE]
    sample_dates = [d for d in sample_dates if len(closes.loc[:d]) >= WINDOW_DAYS]
    n_windows = len(sample_dates)
    out("=" * 72)
    out(f"PLAN §12 Fase 4a — Barrido de cointegración (ventana {WINDOW_DAYS}d, "
        f"muestreo {SAMPLE_STRIDE}d, {n_windows} ventanas)")
    out(f"Pares: C({len(symbols)},2) = {len(symbols) * (len(symbols) - 1) // 2} | "
        f"umbral estabilidad: {MIN_STABLE_PCT:.0%}")
    out("=" * 72)

    pairs = list(itertools.combinations(symbols, 2))
    results = []
    for k, (a, b) in enumerate(pairs):
        if k % 200 == 0:
            print(f"  par {k}/{len(pairs)}", flush=True)
        n_stationary = 0
        for d in sample_dates:
            window = closes.loc[:d].tail(WINDOW_DAYS)
            try:
                if spread_stationary(window[a].values, window[b].values):
                    n_stationary += 1
            except (ValueError, np.linalg.LinAlgError):
                continue
        frac = n_stationary / n_windows if n_windows else 0.0
        results.append({"pair_a": a, "pair_b": b, "n_stationary": n_stationary,
                        "stable_pct": frac})

    df = pd.DataFrame(results).sort_values("stable_pct", ascending=False)
    df.to_parquet(parquet_path)

    stable = df[df["stable_pct"] >= MIN_STABLE_PCT]
    out(f"\n=== RESULTADO (pares = {len(df)}) ===")
    out(f"Pares estables (>= {MIN_STABLE_PCT:.0%} de ventanas): {len(stable)}")
    out(f"\nTop 15 por estabilidad:")
    for _, r in df.head(15).iterrows():
        out(f"  {r['pair_a']:6s} x {r['pair_b']:6s}  stable={r['stable_pct']:.0%} "
            f"({r['n_stationary']}/{n_windows})")

    out(f"\nGate §12.2.2: {'PASA (>= 8 pares estables)' if len(stable) >= 8 else 'NO PASA (< 8 pares) — el proyecto de pares se cierra'}")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
