"""
Fase 1 — diagnóstico de factores fundamentales point-in-time (EDGAR) vs
retornos futuros del universo.

Valida la hipótesis académica de valor/calidad/crecimiento con datos REALES
y point-in-time (filing dates de SEC, precio del día de trading siguiente —
sin lookahead): Fama-French (1992) book-to-market, Basu (1977) E/P, Novy-Marx
(2013) gross profitability, Sloan (1996) ROA/accruals, Bernard-Thomas (1989)
PEAD, etc.

Misma disciplina que los demás diagnósticos: IC con significancia
|IC| > 2/sqrt(n_eff) (Newey-West), terciles direccionales, pre-registro.

NOTA PRE-REGISTRADA: sue_score NO es derivable de EDGAR (requiere
expectativas de consenso de analistas) -> se excluye del diagnóstico y del
backtest de Fase 1. Si el resto de la categoría fundamentales no produce
edge, SUE (PEAD) queda como hipótesis no probada, no como confirmada.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZONS = [5, 20, 60]
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
FUND_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
WARMUP_DAYS = 260
PANEL_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "fundamentals_panel.parquet"

# Los 15 ratios del motor MENOS sue_score (no derivable de EDGAR).
FUNDAMENTAL_COLS = [
    "pe_ratio", "pb_ratio", "ev_ebitda", "roe", "roa", "debt_equity",
    "fcf_yield", "div_yield", "eps_growth", "gross_margin", "peg",
    "current_ratio", "asset_turnover", "book_value_growth",
]

# Dirección esperada según la literatura (SIGN dicta la señal, no al revés):
# negativos = mientras MÁS BAJO el ratio, MEJOR (value); positivos = más alto, mejor.
EXPECTED_SIGN = {
    "pe_ratio": -1,        # Basu 1977: E/P alto (P/E bajo) -> retornos altos
    "pb_ratio": -1,        # Fama-French 1992: book-to-market alto (P/B bajo)
    "ev_ebitda": -1,       # Loughran-Wellman 2011: EV/EBITDA bajo
    "roe": +1,             # Fama-French 2006: rentabilidad alta
    "roa": +1,             # Sloan 1996: calidad de ganancias
    "debt_equity": -1,     # Altman 1968: leverage alto -> riesgo
    "fcf_yield": +1,       # Lakonishok 1994: FCF yield alto
    "div_yield": +1,       # Fama-French 1988: div yield alto
    "eps_growth": +1,      # Chan 1996: momentum en ganancias
    "gross_margin": +1,    # Novy-Marx 2013: profitability premium
    "peg": -1,             # Peters 1991: PEG bajo
    "current_ratio": +1,   # Graham-Dodd 1934: liquidez
    "asset_turnover": +1,  # Fama-French 2006: eficiencia
    "book_value_growth": +1,  # Sloan 1996: crecimiento contable
}


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


def newey_west_neff(records: pd.DataFrame, col: str, horizon: int) -> float:
    """Tamaño de muestra efectivo (Newey-West, pesos Bartlett) para el IC.

    El panel repite el predictor forward-filled y solapa los retornos futuros
    (stride 5d contra horizonte h). Sin corrección, n=14000 infla la
    significancia. Se estima la autocorrelación de z_t = (x-xbar)(y-ybar)
    por símbolo con L = ceil(horizon/stride) lags, y se suman los n_eff por
    símbolo (series entre sí casi independientes).
    """
    fwd_col = f"fwd_{horizon}"
    L = int(np.ceil(horizon / STRIDE_DAYS))
    total = 0.0
    for _, sub in records.groupby("symbol"):
        sub = sub.dropna(subset=[col, fwd_col])
        if len(sub) < 30:
            continue
        x = sub[col].to_numpy()
        y = sub[fwd_col].to_numpy()
        z = (x - x.mean()) * (y - y.mean())
        n = len(z)
        lag_max = min(L, n - 2)
        if lag_max < 1:
            total += n
            continue
        rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
        rho = np.nan_to_num(rho, nan=0.0)
        w = 1 - np.arange(1, len(rho) + 1) / (L + 1)
        denom = 1 + 2 * np.sum(w * rho)
        n_eff_sym = n / max(denom, 1 + L)
        total += n_eff_sym
    return max(total, 30.0)


def collect_records(price_data: dict, fund_panel: pd.DataFrame) -> pd.DataFrame:
    records = []
    fund_panel = fund_panel.reset_index()
    fund_panel["date"] = pd.to_datetime(fund_panel["date"])
    for symbol in SYMBOLS:
        df = price_data.get(symbol)
        if df is None:
            continue
        n = len(df)
        if n < WARMUP_DAYS + max(HORIZONS):
            continue
        has_fund = symbol in FUND_SYMBOLS
        for i in range(WARMUP_DAYS, n - max(HORIZONS), STRIDE_DAYS):
            date = df.index[i]
            row = {"symbol": symbol, "date": date}
            if has_fund:
                sub = fund_panel[(fund_panel["symbol"] == symbol) & (fund_panel["date"] <= date)]
                if len(sub) > 0:
                    fund_row = sub.iloc[-1]
                    for col in FUNDAMENTAL_COLS:
                        v = fund_row.get(col)
                        row[col] = np.nan if pd.isna(v) else float(v)
            entry = df["close"].iloc[i]
            for h in HORIZONS + [1]:
                row[f"fwd_{h}"] = df["close"].iloc[i + h] / entry - 1
            records.append(row)
    return pd.DataFrame(records)


def report_univariate(records: pd.DataFrame, horizon: int):
    fwd = records[f"fwd_{horizon}"]
    n = len(records)
    print(f"\n  IC univariado {horizon}d (n={n}, base_ret={fwd.mean():+.4f}):")
    print(f"    {'col':20s} {'ic':>8s} {'rank_ic':>8s} {'n':>6s} {'n_eff':>7s} {'sig':>5s} {'dir':>4s}")
    results = []
    for col in FUNDAMENTAL_COLS:
        values = records[col]
        mask = values.notna()
        if mask.sum() < 100:
            print(f"    {col:20s}  n={mask.sum()} insuficiente")
            continue
        ic = SignalQualityMetrics.compute_ic(values[mask], fwd[mask])
        rank_ic = SignalQualityMetrics.compute_rank_ic(values[mask], fwd[mask])
        n_eff = newey_west_neff(records, col, horizon)
        thresh = significance_threshold(n_eff)
        sig = " ***" if abs(ic) > thresh else ""
        expected = EXPECTED_SIGN.get(col, 0)
        matches = "ok" if (ic > 0) == (expected > 0) else "REV"
        results.append((col, ic, rank_ic, mask.sum(), n_eff, sig, matches))
    results.sort(key=lambda r: abs(r[1]), reverse=True)
    for col, ic, rank_ic, cnt, n_eff, sig, matches in results:
        print(f"    {col:20s} {ic:+8.4f} {rank_ic:+8.4f} {cnt:6d} {n_eff:7.0f}{sig} {matches}")


def report_terciles(records: pd.DataFrame, horizon: int, col: str, label: str):
    sub = records[records[col].notna()].copy()
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    try:
        sub["bucket"] = pd.qcut(sub[col], 3, labels=["bajo", "medio", "alto"], duplicates="drop")
    except ValueError:
        return
    print(f"    [{label}] retorno {horizon}d por tercil de {col} (base={fwd.mean():+.4f}, n={len(sub)})"
          f" — EVIDENCIA DIRECCIONAL, sin significancia (autocorrelación semanal/solapada):")
    for bucket in ["bajo", "medio", "alto"]:
        cell = sub[sub["bucket"] == bucket]
        print(f"      {bucket:6s}  retorno={cell[f'fwd_{horizon}'].mean():+.4f}  n={len(cell)}")


def main():
    print("Cargando panel EDGAR...")
    fund_panel = pd.read_parquet(PANEL_PATH)
    print(f"Panel: {len(fund_panel)} filas")
    print("Descargando datos de precios...")
    price_data = load_universe(SYMBOLS, "2015-01-01", None)
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}

    records = collect_records(indicators_cache, fund_panel)
    print(f"Registros totales: {len(records)}")

    for horizon in HORIZONS:
        print(f"\n{'='*72}\n=== HORIZONTE {horizon}d ===")
        report_univariate(records, horizon)
        for col in FUNDAMENTAL_COLS:
            report_terciles(records, horizon, col, f"terciles {col}")

    print("\nInterpretación:")
    print("- Dir 'REV' = el IC va en contra de la literatura (p.ej. P/E alto")
    print("  prediciendo retornos altos). Dir 'ok' = dirección esperada.")
    print("- *** = |IC| > 2/sqrt(n_eff): significativo con autocorrelación.")
    print("- sue_score excluido pre-registrado: no es derivable de EDGAR.")
    print("- OJO: el universo es 5 acciones megacap — el corte transversal es")
    print("  chico; la evidencia 'value' histórica vive en el corte transversal")
    print("  amplio. Esto NO es Fama-French sobre 8.000 acciones.")


if __name__ == "__main__":
    main()
