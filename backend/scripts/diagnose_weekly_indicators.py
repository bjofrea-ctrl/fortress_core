"""
PLAN_MEJORA_MATEMATICA §26 (2026-08-17) — Indicadores sobre velas semanales.

HIPÓTESIS: Indicadores calculados sobre velas semanales (resample W-FRI) tienen
menos ruido de microestructura y revelan rank IC significativo contra el retorno
forward de la próxima semana que los indicadores diarios equivalentes no muestran.

MISMO PATRÓN que diagnose_rr2_intraday.py: rank IC intra-semana (Spearman por
semana sobre símbolos) con Newey-West, NO pooled.

Criterio pre-registrado (§26):
  CUMPLE si ≥1 indicador alcanza |t| > 2.73 en ≥2/3 ventanas, signo correcto.
  NO CUMPLE si ninguno lo logra.
  Bonferroni-8: 3 indicadores × 3 ventanas = 9 tests, corrección conservadora.

Metodología: resample('W-FRI'), indicadores sobre serie semanal, fwd_ret_1w.
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

UNIVERSE = [
    "AAPL", "ABBV", "ACN", "ADBE", "AMD", "AMGN", "AMZN", "AVGO", "BAC",
    "BRK-B", "CAT", "CMCSA", "COST", "CRM", "CSCO", "CVX", "DIS", "GE",
    "GOOGL", "HD", "IBM", "INTU", "JNJ", "JPM", "KO", "LIN", "LLY", "MA",
    "MCD", "META", "MRK", "MSFT", "NFLX", "NVDA", "ORCL", "PEP", "PFE",
    "PG", "PM", "QCOM", "QQQ", "SPGI", "SPY", "TMO", "TSLA", "TXN", "UNH",
    "V", "WMT", "XOM",
]

WINDOWS = {
    "W1": ("2019-01-01", "2021-12-31"),
    "W2": ("2022-01-01", "2023-12-31"),
    "W3": ("2024-01-01", "2026-07-06"),
}

FACTORS = {
    "momentum_20w": +1,
    "rsi_14w": +1,
    "adx_14w": +1,
}

MIN_SYMBOLS = 5
LAGS_NW = 1  # ceil(5/5) = 1 lag for weekly forward overlap


def load_weekly_data(cache_dir: str) -> pd.DataFrame:
    """Load daily OHLCV for all symbols, resample to weekly (W-FRI)."""
    frames = []
    for sym in UNIVERSE:
        path = os.path.join(cache_dir, f"{sym}.parquet")
        if not os.path.exists(path):
            print(f"  WARN: {sym}.parquet not found, skipping")
            continue
        df = pd.read_parquet(path)
        df.columns = [c.lower() for c in df.columns]
        weekly = df.resample("W-FRI").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna(subset=["close"])
        if len(weekly) < 30:
            continue
        weekly["symbol"] = sym
        frames.append(weekly)
    if not frames:
        raise SystemExit("No data loaded")
    return pd.concat(frames)


def compute_weekly_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute momentum, RSI, ADX on weekly bars per symbol."""
    result_parts = []
    for sym, g in df.groupby("symbol"):
        g = g.copy()
        # momentum: 20-week return × 100
        g["momentum_20w"] = g["close"].pct_change(20) * 100
        # RSI 14-week
        delta = g["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        g["rsi_14w"] = 100 - (100 / (1 + rs))
        # ADX 14-week (same algorithm as indicators.py)
        plus_dm = g["high"].diff().clip(lower=0)
        minus_dm = -g["low"].diff().clip(upper=0)
        tr = pd.concat([
            g["high"] - g["low"],
            (g["high"] - g["close"].shift()).abs(),
            (g["low"] - g["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        atr_ = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr_
        minus_di = 100 * minus_dm.rolling(14).mean() / atr_
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        g["adx_14w"] = dx.rolling(14).mean()
        # forward return: 1-week ahead
        g["fwd_ret_1w"] = g["close"].shift(-1) / g["close"] - 1
        result_parts.append(g)
    return pd.concat(result_parts)


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusto Newey-West (pesos Bartlett)."""
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


def weekly_rank_ic(panel: pd.DataFrame, factor: str, expected_sign: int) -> dict:
    """Spearman per week (ranks over symbols of THAT week) vs fwd_ret_1w."""
    TARGET = "fwd_ret_1w"
    weekly_ics = []
    weeks = panel["week"].unique()
    for week in weeks:
        w = panel[panel["week"] == week]
        w = w[w[factor].notna() & w[TARGET].notna()]
        if len(w) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(w[factor], w[TARGET])
        if np.isfinite(rho):
            weekly_ics.append(rho)
    ics = np.array(weekly_ics)
    n_weeks = len(ics)
    if n_weeks < 20:
        return {
            "n_weeks": n_weeks, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan,
            "significant": False, "n_sym_avg": 0.0, "weeks_used": 0,
            "weeks_total": len(weeks),
        }
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, LAGS_NW)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    significant = bool(abs(t) > 2.73 and np.sign(mean_ic) == expected_sign)
    return {
        "n_weeks": int(n_weeks),
        "mean_ic": mean_ic,
        "se_nw": se_nw,
        "t": t,
        "significant": significant,
        "n_sym_avg": float(panel.groupby("week").size().mean()),
        "weeks_used": int(n_weeks),
        "weeks_total": int(len(weeks)),
    }


def main():
    cache_dir = os.path.join("data", "cache")
    out_path = os.path.join(
        "data", "cache",
        f"weekly_indicators_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt",
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    out("=" * 72)
    out("§26 — Indicadores sobre velas semanales")
    out("HIPÓTESIS: ruido diario oculta señal en weekly")
    out("=" * 72)

    # Load and resample
    out("\nCargando datos diarios y resampleando a semanal (W-FRI)...")
    raw = load_weekly_data(cache_dir)
    n_symbols_raw = raw["symbol"].nunique()
    out(f"  Símbolos cargados: {n_symbols_raw}")

    # Compute indicators
    out("Calculando indicadores semanales (momentum_20w, rsi_14w, adx_14w)...")
    panel = compute_weekly_indicators(raw)
    panel["week"] = panel.index.to_period("W-FRI").to_timestamp()

    # Summary stats
    out(f"\nSemanas totales: {panel['week'].nunique()}")
    out(f"Símbolos/sem promedio: {panel.groupby('week').size().mean():.1f}")
    out(f"fwd_ret_1w disponible: {panel['fwd_ret_1w'].notna().sum()} / {len(panel)}")

    # Per-window analysis
    results = {}
    for win_name, (start, end) in WINDOWS.items():
        w_start = pd.Timestamp(start)
        w_end = pd.Timestamp(end)
        w_panel = panel[(panel.index >= w_start) & (panel.index <= w_end)].copy()
        n_weeks_win = w_panel["week"].nunique()
        out(f"\n{'='*72}")
        out(f"VENTANA {win_name}: {start} a {end} | {n_weeks_win} semanas")
        out(f"{'='*72}")
        out(f"{'factor':16s} {'n_weeks':>8s} {'mean_IC':>9s} {'SE_NW':>8s} "
            f"{'t':>7s} {'veredicto':>18s}")
        out("-" * 72)
        for factor, sign in FACTORS.items():
            res = weekly_rank_ic(w_panel, factor, sign)
            v = "SIGNIFICATIVO" if res["significant"] else "no sig"
            if res["n_weeks"] < 20:
                v = "NO INTERPRETABLE"
            results[(win_name, factor)] = res
            out(f"{factor:16s} {res['n_weeks']:8d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {v:>18s}")

    # Cross-window summary
    out(f"\n{'='*72}")
    out("RESUMEN CRUZADO (§26)")
    out(f"{'='*72}")
    out(f"Criterio: |t| > 2.73 en ≥2/3 ventanas, signo correcto")
    out(f"Bonferroni-8 (3 indicadores × 3 ventanas, corrección conservadora)")
    out()
    for factor in FACTORS:
        sig_count = sum(
            1 for win in WINDOWS
            if results.get((win, factor), {}).get("significant", False)
        )
        verdict = "CUMPLE" if sig_count >= 2 else "NO CUMPLE"
        out(f"  {factor}: {sig_count}/3 ventanas significativas → {verdict}")
        for win in WINDOWS:
            r = results.get((win, factor), {})
            t_val = r.get("t", float("nan"))
            ic_val = r.get("mean_ic", float("nan"))
            out(f"    {win}: IC={ic_val:+.4f}, t={t_val:+.2f}")

    # Final verdict (pre-registered criterion)
    any_cumple = False
    for factor in FACTORS:
        sig_count = sum(
            1 for win in WINDOWS
            if results.get((win, factor), {}).get("significant", False)
        )
        if sig_count >= 2:
            any_cumple = True
            break

    final = "CUMPLE" if any_cumple else "NO CUMPLE"
    out(f"\n{'='*72}")
    out(f"VEREDICTO §26: {final}")
    out(f"{'='*72}")
    if any_cumple:
        out("Algún indicador semanal tiene señal robusta bajo Bonferroni-8.")
        out("→ Evaluar integración al motor (discutir, no hacer solo).")
    else:
        out("Ningún indicador semanal alcanza significancia bajo Bonferroni-8.")
        out("→ Baseline diario sigue siendo el único modo de operación documentado.")

    out(f"\nArtefacto: {out_path}")
    return final


if __name__ == "__main__":
    sys.exit(main())
