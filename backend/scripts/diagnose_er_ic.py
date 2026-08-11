"""
Diagnóstico V4 — Efficiency Ratio de Kaufman (velocidad del movimiento).

TRIAL #12 (PLAN_SENTIMIENTO.md §9.7, pre-registrado 2026-08-10).

Valida la hipótesis del usuario sobre la velocidad de las subidas/bajadas:
- Movimiento LENTO y eficiente (ER -> 1): "quiere pasar desapercibido" ->
  predice CONTINUACIÓN (subida lenta sigue subiendo; caída lenta sigue cayendo).
- Movimiento RÁPIDO y ruidoso (ER -> 0): "quiere generar entusiasmo/miedo" ->
  predice REVERSIÓN (pico rápido revierte; caída rápida rebota).

Misma disciplina que los otros diagnósticos: IC real contra retornos futuros,
separando tramos alcistas y bajistas (la hipótesis es dependiente de la pata).
Universo: 50 símbolos (7 originales + 43 del proyecto universo 50), datos hasta
2026-08-04. Freno Fase 1: sin IC direccional consistente + terciles no-monótonos
-> V4 se archiva, no llega al backtest (Fase 2 gated, criterio original,
N_TRIALS=18).
"""
import pandas as pd
import numpy as np

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.probabilistic_engine import SignalQualityMetrics
from scripts.fetch_universe_data import NEW_UNIVERSE

HORIZONS = [5, 20, 60]
ER_PERIODS = [10, 20, 60]
LEG_LOOKBACK = 20
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
WARMUP_DAYS = 260


def build_full_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Replica el pipeline de producción: base + predictivos, sin recortar
    salvo en 'close' (mismo criterio que diagnose_bull_bear_ic.py)."""
    d = df.copy()
    with_base = calculate_all_indicators(d)
    for col in with_base.columns:
        if col not in d.columns:
            d[col] = with_base[col]
    d = calculate_predictive_indicators(d)
    return d.dropna(subset=["close"])


def collect_records(price_data: dict) -> pd.DataFrame:
    records = []
    for symbol in SYMBOLS:
        df = price_data.get(symbol)
        if df is None:
            continue
        n = len(df)
        if n < WARMUP_DAYS + max(HORIZONS):
            continue
        for i in range(WARMUP_DAYS, n - max(HORIZONS), STRIDE_DAYS):
            row = {"symbol": symbol}
            entry = df["close"].iloc[i]
            leg_entry = df["close"].iloc[i - LEG_LOOKBACK]
            leg_ret = entry / leg_entry - 1
            row["leg_ret20"] = leg_ret
            row["leg_dir20"] = 1 if leg_ret > 0 else -1
            row["leg_speed20"] = leg_ret / LEG_LOOKBACK
            row["abs_leg_ret20"] = abs(leg_ret)
            for er_p in ER_PERIODS:
                col = f"er{er_p}"
                val = df[col].iloc[i]
                row[col] = None if pd.isna(val) else float(val)
            for h in HORIZONS:
                future = df["close"].iloc[i + h]
                row[f"fwd_{h}"] = future / entry - 1
            records.append(row)
    return pd.DataFrame(records)


def significance_threshold(n: int) -> float:
    return 2.0 / np.sqrt(n)


def report_ic(records: pd.DataFrame, horizon: int, mask=None, label: str = "full sample"):
    sub = records if mask is None else records[mask]
    n = len(sub)
    if n < 100:
        print(f"    n={n} insuficiente")
        return
    fwd = sub[f"fwd_{horizon}"]
    thresh = significance_threshold(n)
    print(f"    [{label}] n={n}  sig_threshold=+/-{thresh:.4f}  base_ret={fwd.mean():+.4f}")
    for er_p in ER_PERIODS:
        col = f"er{er_p}"
        values = sub[col].dropna()
        if len(values) < 100:
            continue
        mask_ok = values.index
        ic = SignalQualityMetrics.compute_ic(values, fwd.loc[mask_ok])
        rank_ic = SignalQualityMetrics.compute_rank_ic(values, fwd.loc[mask_ok])
        sig = "***" if abs(ic) > thresh else ""
        print(f"      er{er_p:3d}  ic={ic:+.4f}  rank_ic={rank_ic:+.4f}  n={len(values)}  {sig}")


def report_terciles(records: pd.DataFrame, horizon: int, mask, label: str):
    sub = records[mask]
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    print(f"    [{label}] retorno futuro {horizon}d por tercil de ER20 "
          f"(base={fwd.mean():+.4f}, n={len(sub)}):")
    try:
        sub = sub.copy()
        sub["er_bucket"] = pd.qcut(sub["er20"], 3, labels=["ER_bajo", "ER_medio", "ER_alto"])
    except ValueError:
        print("      (no alcanzan datos para terciles)")
        return
    for bucket in ["ER_bajo", "ER_medio", "ER_alto"]:
        cell = sub[sub["er_bucket"] == bucket]
        mean_fwd = cell[f"fwd_{horizon}"].mean()
        print(f"      {bucket:9s}  retorno={mean_fwd:+.4f}  n={len(cell)}")


def main():
    print("Descargando datos...")
    price_data = load_universe(SYMBOLS, START, END)
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}
    records = collect_records(indicators_cache)
    print(f"Registros totales: {len(records)}")

    for horizon in HORIZONS:
        print(f"\n{'='*70}\n=== HORIZONTE {horizon}d ===")
        fwd = records[f"fwd_{horizon}"]
        thresh = significance_threshold(len(records))
        print(f"  Base: retorno medio={fwd.mean():+.4f}  sig=+/-{thresh:.4f}")

        print("\n  IC univariado (muestra completa):")
        report_ic(records, horizon)

        up = records["leg_dir20"] > 0
        down = records["leg_dir20"] < 0
        print(f"\n  Tramo ALCISTA (leg_ret20 > 0, n={up.sum()}):")
        print("    IC de ER vs retorno futuro — si subida lenta sigue subiendo, IC > 0;"
              " si el pico rápido revierte, el tercil ER_bajo debe dar negativo:")
        report_ic(records, horizon, mask=up.values, label="up legs")
        report_terciles(records, horizon, up.values, "up legs")
        print("    Velocidad del tramo: |leg_ret20| alto (pico) debe predecir reversión -> IC( |leg_ret|, fwd ) < 0:")
        values = records.loc[up, "abs_leg_ret20"]
        fwd_up = records.loc[up, f"fwd_{horizon}"]
        if len(values) > 100:
            ic = SignalQualityMetrics.compute_ic(values, fwd_up)
            print(f"      ic(abs_leg_ret20)={ic:+.4f}  n={len(values)}")

        print(f"\n  Tramo BAJISTA (leg_ret20 < 0, n={down.sum()}):")
        print("    IC de ER vs retorno futuro — si caída rápida rebota (fwd > 0) y caída"
              " lenta sigue cayendo (fwd < 0), el IC debe ser NEGATIVO:")
        report_ic(records, horizon, mask=down.values, label="down legs")
        report_terciles(records, horizon, down.values, "down legs")
        values = records.loc[down, "abs_leg_ret20"]
        fwd_down = records.loc[down, f"fwd_{horizon}"]
        if len(values) > 100:
            ic = SignalQualityMetrics.compute_ic(values, fwd_down)
            print(f"      ic(abs_leg_ret20)={ic:+.4f}  n={len(values)}")

    print("\nInterpretación (V4):")
    print("- Subida lenta/eficiente (ER alto) predice continuación -> IC(er, fwd) > 0 en tramos alcistas")
    print("- Subida rápida/ruidosa (ER bajo) predice reversión -> tercil ER_bajo con retorno < 0 en tramos alcistas")
    print("- Caída lenta/persistente sigue cayendo y caída rápida rebota -> IC(er, fwd) < 0 en tramos bajistas")


if __name__ == "__main__":
    main()
