"""
Diagnóstico ola 1 — Sentimiento (COT) y liquidez (FRED) vs retornos futuros.

Valida las hipótesis H5/H6 de la Fase E.1 v3:
- H5 (posicionamiento): el neto especulativo/retail/institucional del COT del
  E-MINI S&P 500 predice el retorno futuro del universo. La tesis del usuario:
  retail/inversores posicionados en el mismo lado del mercado = institución
  distribuye -> caída; posicionamiento en contra = institución acumula -> subida.
- H6 (liquidez): WALCL/reservas en crecimiento y reverse repo en caída (liquidez
  liberada) habilitan el mecanismo -> retornos futuros positivos; e interactúa
  con el sentimiento (2x2: liquidez alta/baja x sentimiento extremo).
- Paso 2 (cuestionar las demás variables): IC de momentum/RSI/ER DENTRO de cada
  bucket de sentimiento y de liquidez — si una variable pierde poder predictivo
  en un estado de sentimiento extremo, esa es la evidencia para modular su peso.

Misma disciplina que los demás diagnósticos: datos reales, IC con significancia
|IC| > 2/sqrt(n), dirección dictada por los datos, no por la narrativa.
"""
import pandas as pd
import numpy as np

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.market_sentiment import build_sentiment_frame
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZONS = [5, 20, 60]
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
WARMUP_DAYS = 260

SENTIMENT_COLS = [
    "cot_lev_net_pct",
    "cot_asset_net_pct",
    "cot_retail_net_pct",
    "cot_dealer_net_pct",
    "walcl_growth_w",
    "wresbal_growth_w",
]
LIQUIDITY_COLS = ["walcl_growth_w", "wresbal_growth_w"]


def build_full_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    with_base = calculate_all_indicators(d)
    for col in with_base.columns:
        if col not in d.columns:
            d[col] = with_base[col]
    d = calculate_predictive_indicators(d)
    return d.dropna(subset=["close"])


def significance_threshold(n: int) -> float:
    return 2.0 / np.sqrt(n)


def collect_records(price_data: dict, sentiment: pd.DataFrame) -> pd.DataFrame:
    records = []
    for symbol in SYMBOLS:
        df = price_data.get(symbol)
        if df is None:
            continue
        n = len(df)
        if n < WARMUP_DAYS + max(HORIZONS):
            continue
        for i in range(WARMUP_DAYS, n - max(HORIZONS), STRIDE_DAYS):
            date = df.index[i]
            if date not in sentiment.index:
                continue
            row = {"symbol": symbol}
            for col in SENTIMENT_COLS:
                row[col] = sentiment.loc[date, col]
            row["rsi14"] = df["rsi14"].iloc[i]
            row["momentum_12_1"] = df["momentum_12_1"].iloc[i] if "momentum_12_1" in df else np.nan
            row["er20"] = df["er20"].iloc[i]
            entry = df["close"].iloc[i]
            for h in HORIZONS:
                row[f"fwd_{h}"] = df["close"].iloc[i + h] / entry - 1
            records.append(row)
    return pd.DataFrame(records)


def report_univariate(records: pd.DataFrame, horizon: int):
    fwd = records[f"fwd_{horizon}"]
    n = len(records)
    thresh = significance_threshold(n)
    print(f"\n  IC univariado {horizon}d (n={n}, sig=+/-{thresh:.4f}, base_ret={fwd.mean():+.4f}):")
    print(f"    {'col':22s} {'ic':>8s} {'rank_ic':>8s} {'n':>6s}")
    results = []
    for col in SENTIMENT_COLS:
        values = records[col]
        mask = values.notna()
        if mask.sum() < 100:
            print(f"    {col:22s}  n={mask.sum()} insuficiente")
            continue
        ic = SignalQualityMetrics.compute_ic(values[mask], fwd[mask])
        rank_ic = SignalQualityMetrics.compute_rank_ic(values[mask], fwd[mask])
        results.append((col, ic, rank_ic, mask.sum()))
    results.sort(key=lambda r: abs(r[1]), reverse=True)
    for col, ic, rank_ic, cnt in results:
        sig = " ***" if abs(ic) > thresh else ""
        print(f"    {col:22s} {ic:+8.4f} {rank_ic:+8.4f} {cnt:6d}{sig}")


def report_terciles(records: pd.DataFrame, horizon: int, col: str, label: str):
    sub = records[records[col].notna()].copy()
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    try:
        sub["bucket"] = pd.qcut(sub[col], 3, labels=["bajo", "medio", "alto"], duplicates="drop")
    except ValueError:
        return
    print(f"    [{label}] retorno {horizon}d por tercil de {col} (base={fwd.mean():+.4f}, n={len(sub)}):")
    for bucket in ["bajo", "medio", "alto"]:
        cell = sub[sub["bucket"] == bucket]
        print(f"      {bucket:6s}  retorno={cell[f'fwd_{horizon}'].mean():+.4f}  n={len(cell)}")


def report_liquidity_x_sentiment(records: pd.DataFrame, horizon: int):
    """H6: tabla 2x2 liquidez (WALCL growth alta/baja) x retail COT (alto/bajo)."""
    sub = records[records[["walcl_growth_w", "cot_retail_net_pct"]].notna().all(axis=1)].copy()
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    try:
        sub["liq_bucket"] = pd.qcut(sub["walcl_growth_w"], 2, labels=["liq_baja", "liq_alta"], duplicates="drop")
        sub["ret_bucket"] = pd.qcut(sub["cot_retail_net_pct"], 2, labels=["ret_baja", "ret_alta"], duplicates="drop")
    except ValueError:
        return
    print(f"\n  [H6] 2x2 liquidez x retail COT, retorno {horizon}d (base={fwd.mean():+.4f}):")
    for liq in ["liq_baja", "liq_alta"]:
        row = []
        for ret in ["ret_baja", "ret_alta"]:
            cell = sub[(sub["liq_bucket"] == liq) & (sub["ret_bucket"] == ret)]
            row.append(f"{cell[f'fwd_{horizon}'].mean():+.4f} (n={len(cell)})")
        print(f"      {liq:9s} | ret_baja: {row[0]} | ret_alta: {row[1]}")


def report_conditional_ic(records: pd.DataFrame, horizon: int):
    """Paso 2: IC de momentum/rsi/er DENTRO de cada bucket de sentimiento y
    liquidez — el 'cuestionar las demás variables contra la principal'."""
    factors = [("momentum_12_1", "momentum"), ("rsi14", "rsi"), ("er20", "er")]
    for cond_col in ["cot_retail_net_pct", "cot_lev_net_pct", "walcl_growth_w"]:
        sub = records[records[cond_col].notna()].copy()
        if len(sub) < 150:
            continue
        try:
            sub["bucket"] = pd.qcut(sub[cond_col], 3, labels=["bajo", "medio", "alto"], duplicates="drop")
        except ValueError:
            continue
        print(f"\n  [Paso 2] IC de cada factor DENTRO de buckets de {cond_col} ({horizon}d):")
        print(f"    {'bucket':7s} {'factor':10s} {'ic':>8s} {'n':>6s}")
        for bucket in ["bajo", "medio", "alto"]:
            cell = sub[sub["bucket"] == bucket]
            fwd = cell[f"fwd_{horizon}"]
            for col, name in factors:
                values = cell[col]
                mask = values.notna() & fwd.notna()
                if mask.sum() < 100:
                    continue
                ic = SignalQualityMetrics.compute_ic(values[mask], fwd[mask])
                print(f"    {bucket:7s} {name:10s} {ic:+8.4f} {mask.sum():6d}")


def main():
    print("Descargando datos...")
    price_data = load_universe(SYMBOLS, "2019-01-01", "2024-12-31")
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}

    trading_dates = indicators_cache["SPY"].index
    print("Construyendo panel de sentimiento/liquidez (FRED + COT)...")
    sentiment = build_sentiment_frame(trading_dates)
    print(f"Panel: {len(sentiment)} filas, {len(sentiment.columns)} columnas")
    print(sentiment[["cot_retail_net_pct", "cot_lev_net_pct", "walcl_growth_w"]].describe().to_string())

    records = collect_records(indicators_cache, sentiment)
    print(f"Registros totales: {len(records)}")

    for horizon in HORIZONS:
        print(f"\n{'='*72}\n=== HORIZONTE {horizon}d ===")
        report_univariate(records, horizon)
        for col in ["cot_retail_net_pct", "cot_lev_net_pct", "walcl_growth_w"]:
            report_terciles(records, horizon, col, f"terciles {col}")
        report_liquidity_x_sentiment(records, horizon)
        report_conditional_ic(records, horizon)

    print("\nInterpretación:")
    print("- H5: si el IC de cot_*_net es NEGATIVO, posicionamiento alto (retail/specs")
    print("  comprados) predice caída — confirma 'instituciones distribuyen a retail'.")
    print("- H6: si walcl_growth_w es POSITIVO, más liquidez -> retornos más altos;")
    print("  la celda liq_alta x ret_baja debe ser la más alta del 2x2.")


if __name__ == "__main__":
    main()
