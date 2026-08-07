"""
Mide el IC real de cada regla de _macro_signals (predictive_engine.py) contra
retornos futuros de acciones reales — la misma disciplina que ya se aplicó a
signal_engine.py (diagnose_factor_ic), extendida a las señales macro.

Reusa la lógica de producción tal cual (llama a PredictiveEngine._macro_signals
directamente) en vez de reimplementarla vectorizada, para no arriesgar una
divergencia sutil con lo que el sistema real calcula.
"""
from datetime import datetime
import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.predictive_engine import PredictiveEngine
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZON_DAYS = 20
STRIDE_DAYS = 5  # semanal, mismo criterio que el resto de los diagnósticos de hoy


def main():
    tickers = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    market_tickers = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX",
                       "DX-Y.NYB", "GC=F", "SI=F", "CL=F", "HG=F"]

    print("Descargando datos...")
    price_data = load_universe(tickers, "2019-01-01", "2024-12-31")
    market_data = load_universe(market_tickers, "2015-01-01", "2024-12-31")

    # _macro_signals espera estas claves específicas
    macro_data = {
        "DXY": market_data.get("DX-Y.NYB"), "gold": market_data.get("GC=F"),
        "silver": market_data.get("SI=F"), "TLT": market_data.get("TLT"),
        "SPY": market_data.get("SPY"), "oil": market_data.get("CL=F"),
        "copper": market_data.get("HG=F"),
    }
    macro_data = {k: v for k, v in macro_data.items() if v is not None}

    engine = PredictiveEngine()

    start_date = datetime(2019, 1, 1)
    end_date = datetime(2024, 12, 31)
    spy_dates = market_data["SPY"]
    dates = spy_dates[(spy_dates.index >= start_date) & (spy_dates.index <= end_date)].index

    pooled = {}  # signal_name -> list of values
    pooled_returns_by_signal = {}  # signal_name -> list of forward returns
    composite_values, composite_returns = [], []

    print(f"Evaluando {len(dates)} fechas (stride={STRIDE_DAYS})...")
    for i in range(0, len(dates) - HORIZON_DAYS, STRIDE_DAYS):
        date = dates[i]
        sliced_macro = {k: df[df.index <= date] for k, df in macro_data.items()}
        signals, composite = engine._macro_signals(sliced_macro)
        if not signals:
            continue

        for symbol in tickers:
            df = price_data.get(symbol)
            if df is None or date not in df.index:
                continue
            pos = df.index.get_loc(date)
            if pos + HORIZON_DAYS >= len(df):
                continue
            entry = df["close"].iloc[pos]
            future = df["close"].iloc[pos + HORIZON_DAYS]
            fwd_return = future / entry - 1

            for sig in signals:
                pooled.setdefault(sig.name, []).append(sig.signal)
                pooled_returns_by_signal.setdefault(sig.name, []).append(fwd_return)

            composite_values.append(composite)
            composite_returns.append(fwd_return)

    print("\n=== IC POR REGLA MACRO (pooled, todos los símbolos) ===")
    results = []
    for name, values in pooled.items():
        returns = pooled_returns_by_signal[name]
        ic = SignalQualityMetrics.compute_ic(pd.Series(values), pd.Series(returns))
        rank_ic = SignalQualityMetrics.compute_rank_ic(pd.Series(values), pd.Series(returns))
        results.append((name, ic, rank_ic, len(values)))

    results.sort(key=lambda r: abs(r[1]), reverse=True)
    for name, ic, rank_ic, n in results:
        print(f"{name:40s}  ic={ic:+.4f}  rank_ic={rank_ic:+.4f}  n={n}")

    comp_ic = SignalQualityMetrics.compute_ic(pd.Series(composite_values), pd.Series(composite_returns))
    comp_rank_ic = SignalQualityMetrics.compute_rank_ic(pd.Series(composite_values), pd.Series(composite_returns))
    print(f"\n=== SCORE MACRO COMPUESTO (blend actual de _macro_signals) ===")
    print(f"ic={comp_ic:+.4f}  rank_ic={comp_rank_ic:+.4f}  n={len(composite_values)}")


if __name__ == "__main__":
    main()
