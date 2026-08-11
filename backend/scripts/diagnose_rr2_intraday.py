"""
PLAN_MEJORA_MATEMATICA §4.1 / Fase 0.5a (2026-08-11) — rank IC INTRA-DÍA.

La corrección más importante de la auditoría #2: el rank_ic POOLED (2069
filas de 50 símbolos concatenadas) mezcla la dimensión temporal con la
transversal: si momentum sube para TODOS los símbolos el mismo día (rally),
infla el Spearman pooled sin que exista jerarquía intra-día real.

El test correcto para "selección vs timing" (W2 vs W3, §4.5):
  Por cada fecha elegible del panel: rankear los símbolos disponibles por
  el factor, correlacionar (Spearman) con el retorno forward 20d, promediar
  sobre fechas con error estándar Newey-West (solapamiento temporal del
  retorno forward: L = ceil(horizon/stride) lags, pesos Bartlett).

Criterio pre-registrado (gate §4.5):
  - |mean_rank_ic| > 2 * se_nw (t significativo) y signo correcto ->
    hay jerarquía cross-sectional real -> consistente con W3 (selección).
  - No significativo -> consistente con W2 (timing, no selección).
  Este script NO decide el gate solo: corre en paralelo con 0.5b (RMT) y
  0.5c (ridge macro crudo). El veredicto es conjunto.

Nota de diseño: con n_símbolos chico por fecha, el Spearman por fecha está
sesgado hacia ±1 por ruido — la significancia viene de la distribución
temporal de los ICs (n fechas), NO del n por fecha. Por eso el promedio
sobre fechas con Newey-West, no el pooled.
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

FACTORS = {
    "momentum_score": +1,  # esperado: mayor momentum -> mayor retorno
    "rsi_score": +1,
    "trend_score": +1,
    "adx_score": +1,
}
TARGET = "fwd_return_20d"
HORIZON = 20
STRIDE_DAYS = 5          # mismo stride del panel
MIN_SYMBOLS = 5          # mínimo de símbolos por fecha para computar el Spearman
L = int(np.ceil(HORIZON / STRIDE_DAYS))  # lags Newey-West


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet — corre build_factor_panel.py")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusto Newey-West (pesos Bartlett) para una serie temporal."""
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


def intraday_rank_ic(panel: pd.DataFrame, factor: str, expected_sign: int) -> dict:
    """Spearman por fecha (ranks sobre símbolos de ESA fecha) vs fwd 20d."""
    daily_ics = []
    dates = panel["date"].unique()
    for date in dates:
        day = panel[panel["date"] == date]
        day = day[day[factor].notna() & day[TARGET].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day[factor], day[TARGET])
        if np.isfinite(rho):
            daily_ics.append(rho)
    ics = np.array(daily_ics)
    n_days = len(ics)
    if n_days == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan,
                "significant": False, "n_sym_avg": 0.0, "days_used": 0, "days_total": len(dates)}

    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, L)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    significant = bool(abs(t) > 2.0 and np.sign(mean_ic) == expected_sign)
    return {
        "n_days": int(n_days),
        "mean_ic": mean_ic,
        "se_nw": se_nw,
        "t": t,
        "significant": significant,
        "n_sym_avg": float(panel.groupby("date").size().mean()),
        "days_used": int(n_days),
        "days_total": int(len(dates)),
    }


def pooled_rank_ic(panel: pd.DataFrame, factor: str) -> float:
    """Rank IC pooled (la especificación INCORRECTA §3.5/§4.1) — solo para
    documentar el contraste entre las dos especificaciones."""
    sub = panel[panel[factor].notna() & panel[TARGET].notna()]
    if len(sub) < 30:
        return np.nan
    rho, _ = stats.spearmanr(sub[factor], sub[TARGET])
    return float(rho)


def main():
    path = latest_panel()
    out_path = os.path.join("data", "cache", f"rr2_intraday_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    panel = pd.read_parquet(path)
    df = panel[panel["eligible"] & panel[TARGET].notna()].copy()
    df = df.sort_values("date")

    out("=" * 72)
    out("FASE 0.5a (§4.1) — rank IC INTRA-DÍA con Newey-West")
    out(f"Panel: {os.path.basename(path)} | filas eligible: {len(df)}")
    out(f"Horizonte: {HORIZON}d | stride: {STRIDE_DAYS}d | lags NW: {L} | min símbolos/fecha: {MIN_SYMBOLS}")
    out(f"Criterio: |t| > 2 y signo esperado -> significativo (W3); no -> W2.")
    out("=" * 72)

    out(f"\nFechas en panel: {df['date'].nunique()} | símbolos/fecha promedio: {df.groupby('date').size().mean():.1f}")
    out(f"\n{'factor':16s} {'n_days':>7s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'pooled':>9s} {'veredicto':>12s}")
    verdicts = {}
    for factor, sign in FACTORS.items():
        res = intraday_rank_ic(df, factor, sign)
        pooled = pooled_rank_ic(df, factor)
        v = "SIGNIFICATIVO (W3)" if res["significant"] else "no sig (W2)"
        verdicts[factor] = res["significant"]
        out(f"{factor:16s} {res['n_days']:7d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {pooled:+9.4f} {v:>12s}")

    out("\n--- INTERPRETACIÓN (§4.1) ---")
    out("  El pooled se incluye SOLO para documentar el contraste de")
    out("  especificación: puede diferir del intra-día (inflado por el")
    out("  movimiento común del mercado). El que decide es el intra-día.")
    out("  Veredicto conjunto del gate: lo dan 0.5a + 0.5b (RMT) + 0.5c (ridge).")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
