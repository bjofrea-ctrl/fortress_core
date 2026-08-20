"""
PLAN_MEJORA_MATEMATICA §37 (2026-08-20) — T1.1: diagnóstico de IC del proxy OFI.

Test pre-registrado en §37, escrito ANTES de correr. Familia signal_diagnosis,
n_trials=20 (19 consumidos + 1), umbral Bonferroni de la familia:
   |t| > z(1 - 0.05/40) = 3.023  (dos colas, n=20)

HIPÓTESIS: ofi_ewma_fast z-rodante-causal (100d, min_periods=50) predice
fwd_return_20d con signo +1 (cierre al high de barra, presión compradora
sostenida vs. historia reciente del símbolo -> mayor retorno futuro).

MÉTODO (protocolo estándar de la familia, §25/§27/§28/§36):
   - Panel: universo 50, todas las fechas con columna no-NaN (SIN mask de engine).
   - Feats: z rodante 100d por símbolo de ofi_raw / ofi_ewma_fast / ofi_ewma_slow
     (ofi_spike_z del pipeline ya es rolling 100d -> se usa tal cual).
   - Rank IC = Spearman cross-sectional por fecha vs fwd_20.
   - SE Newey-West (L = min(12, n_dias//8)), t = mean_IC / SE_NW.
   - Ventanas W1 2020-2021, W2 2022-2023, W3 2024->2026-07-06 (igual a §25/§36).

CRITERIO (pre-registrado en §37, UN slot en el ledger):
   ofi_ewma_fast_z: |t| > 3.023 con signo +1 en >= 2/3 ventanas -> CUMPLE.
   Las otras feats se reportan con su t pero NO disparan el veredicto.

Reglas: Python 3.9 real (backend/.venv). NO toca indicators.py/signal_engine.py/
trial_registry.py/market.py/live.py/predict.py. Lee el cache, no descarga nada.
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from scipy import stats

START = "2018-01-01"
DATA_END = "2026-08-14"
MIN_SYMBOLS = 5

# Umbral Bonferroni de la familia signal_diagnosis (n_trials=20, dos colas)
ALPHA_PER = 0.05 / (2 * 20)
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))  # 3.023

WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}

Z_WINDOW = 100
Z_MIN_PERIODS = 50

# Features medidas (z rodante por símbolo) y la principal declarada en §37.
FACTOR_COLS = {
    "ofi_raw": "ofi_raw",
    "ofi_ewma_fast": "ofi_ewma_fast",
    "ofi_ewma_slow": "ofi_ewma_slow",
}
Z_SUFFIX = "_z"
MAIN_FEATURE = "ofi_ewma_fast" + Z_SUFFIX


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusto Newey-West (pesos Bartlett) — copia fiel de la de §0.5a/§25."""
    n = len(z)
    if n < 3:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    lag_max = min(lags, n - 2)
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (lags + 1)
    denom = 1 + 2 * np.sum(w * rho)
    n_eff = n / max(denom, 1.0)
    return float(np.std(z, ddof=1) / np.sqrt(n_eff))


def daily_ics(panel: pd.DataFrame, factor: str, target: str, min_sym: int = MIN_SYMBOLS) -> np.ndarray:
    """Spearman por fecha (ranks sobre símbolos de ESA fecha) factor vs target."""
    ics = []
    for _date, day in panel.groupby("date"):
        d = day[[factor, target]].dropna()
        if len(d) < min_sym:
            continue
        rho, _ = stats.spearmanr(d[factor], d[target])
        if np.isfinite(rho):
            ics.append(rho)
    return np.array(ics)


def rank_ic_stats(ics: np.ndarray, lags: int) -> dict:
    n = len(ics)
    if n == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(n), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def rolling_z(series: pd.Series) -> pd.Series:
    """z-score rodante ESTRICTAMENTE CAUSAL (ventana trailing, min_periods=50).

    Cada fecha usa solo historia <= t: hace al z-rate comparable entre símbolos
    (distinta escala de volumen) sin introducir look-ahead.
    """
    mean = series.rolling(Z_WINDOW, min_periods=Z_MIN_PERIODS).mean()
    std = series.rolling(Z_WINDOW, min_periods=Z_MIN_PERIODS).std()
    return (series - mean) / (std + 1e-12)


def build_panel() -> pd.DataFrame:
    price_data = load_universe(SYMBOLS, START, DATA_END)
    frames = []
    for sym, df in price_data.items():
        ind = calculate_all_indicators(df)
        if ind.empty:
            continue
        ind = ind.copy()
        ind["symbol"] = sym
        # z rodante causal por símbolo para las 3 feats raw (ver §37 diseño 2);
        # ofi_spike_z del pipeline ya es z rodante -> se usa sin re-transformar.
        for base_col in FACTOR_COLS:
            ind[base_col + Z_SUFFIX] = rolling_z(ind[base_col])
        ind["fwd_20"] = ind["close"].shift(-20) / ind["close"] - 1
        cols = ["date", "symbol", "close"]
        cols += [c + Z_SUFFIX for c in FACTOR_COLS] + ["ofi_spike_z", "fwd_20"]
        ind.index.name = "date"
        frames.append(ind.reset_index()[cols])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values("date").reset_index(drop=True)


def main() -> int:
    out_path = os.path.join(
        "data", "cache",
        f"trial_ofi_proxy_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §37 — T1.1: diagnóstico de IC del proxy OFI")
    out(f"Umbral familia signal_diagnosis (n=20, dos colas): |t| > {THRESHOLD:.3f}")
    out("Ventanas: " + ", ".join(f"{k} {v[0].date()}->{v[1].date()}" for k, v in WINDOWS.items()))
    out("Feats: z rodante causal 100d por símbolo (min_periods=50); target fwd_20")
    out("=" * 78)

    panel = build_panel()
    out(f"\nPanel: {len(panel)} filas | {panel['date'].nunique()} fechas | "
        f"{panel['symbol'].nunique()} símbolos")
    out(f"Rango fechas: {panel['date'].min().date()} -> {panel['date'].max().date()}")

    def window_stats(sub, factor):
        ics = daily_ics(sub, factor, "fwd_20")
        L = min(12, len(ics) // 8) if len(ics) else 0
        return rank_ic_stats(ics, L), L

    feature_results = {}  # {feat: {window: stats}}
    feature_cols = [c + Z_SUFFIX for c in FACTOR_COLS] + ["ofi_spike_z"]

    out("\nRank IC por ventana, por feature (signo esperado: +1)")
    header = f"{'feature':18s} {'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s} {'sig+':>5s}"
    out(header)
    out("-" * len(header))
    for feat in feature_cols:
        feature_results[feat] = {}
        for name, (start, end) in WINDOWS.items():
            w = panel[(panel["date"] >= start) & (panel["date"] <= end)]
            res, L = window_stats(w, feat)
            feature_results[feat][name] = res
            sig = "SIG+" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and res["t"] > 0) else "no"
            out(f"{feat:18s} {name:7s} {res['n_days']:6d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {L:3d} {sig:>5s}")

    # TOTAL (per feature, no dispara veredicto — solo info)
    out("\nTOTAL por feature (solo informativo, NO pre-registrado)")
    out(f"{'feature':18s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s}")
    for feat in feature_cols:
        res, _ = window_stats(panel, feat)
        out(f"{feat:18s} {res['n_days']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} {res['t']:+7.2f}")

    # Veredicto: MAIN_FEATURE con |t|>THRESHOLD y signo +1 en >=2/3 ventanas
    main_by_win = feature_results[MAIN_FEATURE]
    n_sig = sum(1 for r in main_by_win.values()
                if np.isfinite(r["t"]) and abs(r["t"]) > THRESHOLD and r["t"] > 0)
    cumple = n_sig >= 2
    out("\n" + "=" * 78)
    out(f"CRITERIO §37: {MAIN_FEATURE}: |t| > {THRESHOLD:.3f} con signo +1 en >= 2/3 ventanas")
    out(f"Ventanas SIG+ de {MAIN_FEATURE}: {n_sig}/3 -> "
        f"{'CUMPLE' if cumple else 'NO_CUMPLE'}")
    out("=" * 78)
    out(f"\nOut: {out_path}")
    print(f"\nARTIFACT:{out_path}")
    print(f"VEREDICTO:{'CUMPLE' if cumple else 'NO_CUMPLE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
