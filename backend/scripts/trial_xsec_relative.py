"""
PLAN_MEJORA_MATEMATICA §28 (2026-08-17) — mediciones justas que nunca se hicieron.

Test pre-registrado (ver PLAN_MEJORA_MATEMATICA.md §28, escrito ANTES de correr):

1. TEST A: rank IC intra-dia de momentum/rsi/adx contra retorno RELATIVO a SPY
   (fwd_return_20d - spy_fwd_20d), por ventana W1/W2/W3, Spearman por fecha +
   Newey-West, L = min(12, n_dias//8). Signo esperado +1.
2. TEST B: AAII (sentiment_v1, constante por fecha) como TIMING: Spearman entre el
   spread de la fecha y el mean(rel) del cross-section elegible. Signo esperado -1.
3. CHEQUE DE FIDELIDAD: reproducir §0.5a con target ABSOLUTO (momentum -0.0100/-0.28,
   rsi +0.0404/+1.38, adx +0.0679/+2.31, n 187/164/151, L=4). Falla -> exit 2.

Criterio unico: |t| > 2.86 (Bonferroni-12 bilateral) con signo pre-registrado
en >=2/3 ventanas. 12 tests formales.

Reglas: Python 3.9, NO toca el motor ni el panel; solo lectura.
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

BENCH = "SPY"
HORIZON = 20
MIN_SYMBOLS = 5
FACTORS = ["momentum_score", "rsi_score", "adx_score"]

# Fidelidad §0.5a (artefacto rr2_intraday_20260811_150741.txt), target absoluto, L=4.
FIDELITY = {
    "momentum_score": (187, -0.0100, -0.28),
    "rsi_score": (164, +0.0404, +1.38),
    "adx_score": (151, +0.0679, +2.31),
}
TOL_IC = 0.001
TOL_T = 0.05

ALPHA_PER = 0.05 / 24.0  # 12 tests -> Bonferroni-12 bilateral
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))

WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE Newey-West con pesos Bartlett — copia fiel de §0.5a/§25."""
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


def spy_forward_return(close: pd.Series, date, horizon: int) -> float:
    """Retorno del bench HORIZON ruedas desde `date` (misma aproximación de ruedas
    de trading del bench que §27)."""
    idx = close.index
    pos = idx.searchsorted(date, side="right")  # primera rueda POSTERIOR a date
    if pos >= len(idx) or pos + horizon - 1 >= len(idx):
        return np.nan
    # rueda de partida: la última rueda <= date
    start = idx.searchsorted(date, side="right") - 1
    if start < 0:
        return np.nan
    return float(close.iloc[start + horizon] / close.iloc[start] - 1.0)


def daily_ics(df: pd.DataFrame, factor: str, target: str) -> np.ndarray:
    """Serie de rank IC (Spearman) por fecha — patrón §0.5a/§25."""
    ics = []
    for _date, day in df.groupby("date"):
        day = day[day[factor].notna() & day[target].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day[factor], day[target])
        if np.isfinite(rho):
            ics.append(rho)
    return np.array(ics)


def ic_stats(ics: np.ndarray, lags: int) -> dict:
    n = len(ics)
    if n == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan}
    mean_ic = float(ics.mean())
    se = newey_west_se(ics, lags)
    t = mean_ic / se if se > 0 else 0.0
    return {"n_days": int(n), "mean_ic": mean_ic, "se_nw": se, "t": t}


def main() -> int:
    out_path = os.path.join(
        "data", "cache", f"trial_xsec_relative_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    )

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    panel_path = latest_panel()
    panel = pd.read_parquet(panel_path)
    df = panel[panel["eligible"] & panel["fwd_return_20d"].notna()].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §28 — mediciones justas (2026-08-17)")
    out(f"Panel: {os.path.basename(panel_path)} | filas eligible+target: {len(df)}")
    out(f"Umbral unico pre-registrado: |t| > {THRESHOLD:.3f} (Bonferroni-12 bilateral) "
        f"con signo pre-registrado en >=2/3 ventanas")
    out("=" * 78)

    # --- Target relativo: ret 20 ruedas de SPY por fecha del panel ---
    spy_close = pd.read_parquet(os.path.join("data", "cache", f"{BENCH}.parquet"))["Close"]
    spy_close.index = pd.to_datetime(spy_close.index)
    spy_close = spy_close.sort_index()
    spy_fwd = pd.Series(
        {d: spy_forward_return(spy_close, d, HORIZON) for d in df["date"].unique()}
    )
    df["spy_fwd_20d"] = df["date"].map(spy_fwd)
    n_no_bench = int(df["spy_fwd_20d"].isna().sum())
    df_rel = df[df["spy_fwd_20d"].notna()].copy()
    df_rel["rel"] = df_rel["fwd_return_20d"] - df_rel["spy_fwd_20d"]
    out(f"\nTarget relativo: rel = fwd_return_20d - SPY_fwd_20d. Sin bench: {n_no_bench} filas.")

    # --- Cheque de fidelidad §0.5a (target ABSOLUTO, L=4) ---
    out("\n--- CHEQUE DE FIDELIDAD contra §0.5a (target absoluto, L=4) ---")
    ok = True
    for factor, (n_ref, ic_ref, t_ref) in FIDELITY.items():
        ics = daily_ics(df, factor, "fwd_return_20d")
        res = ic_stats(ics, 4)
        d_ic = abs(res["mean_ic"] - ic_ref)
        d_t = abs(res["t"] - t_ref)
        passed = d_ic <= TOL_IC and d_t <= TOL_T
        ok = ok and passed
        out(f"  {factor:18s} n={res['n_days']:3d}(ref {n_ref}) mean_IC={res['mean_ic']:+.4f}"
            f"(ref {ic_ref:+.4f}) t={res['t']:+.2f}(ref {t_ref:+.2f}) -> "
            f"{'OK' if passed else 'FALLO'}")
    if not ok:
        out("  -> ABORTA sin interpretar (§14): la reimplementación no reproduce la evidencia")
        return 2
    out("  OK: reproduce §0.5a dentro de tolerancia")

    # --- TEST A: rank IC contra retorno relativo ---
    out("\n--- TEST A (pre-registrado §28): rank IC contra retorno RELATIVO por ventana ---")
    out(f"{'factor':18s} {'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} "
        f"{'t':>7s} {'L':>3s} {'signo':>5s} {'SIG':>5s}")
    for factor in FACTORS:
        n_sig = 0
        for name, (start, end) in WINDOWS.items():
            wdf = df_rel[(df_rel["date"] >= start) & (df_rel["date"] <= end)]
            ics = daily_ics(wdf, factor, "rel")
            L = min(12, len(ics) // 8)
            res = ic_stats(ics, L)
            signo = "+" if (np.isfinite(res["t"]) and res["t"] > 0) else "-"
            sig = "SIG" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and signo == "+") else "no"
            if sig == "SIG":
                n_sig += 1
            out(f"{factor:18s} {name:7s} {res['n_days']:6d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {L:3d} {signo:>5s} {sig:>5s}")
        out(f"{'':18s} -> CUMPLE({factor}) si >=2/3: {'SI' if n_sig >= 2 else 'no'} ({n_sig}/3)")

    # --- TEST B: AAII como timing de fecha ---
    out("\n--- TEST B (pre-registrado §28): AAII timing — spread vs mean(rel) por fecha ---")
    out("Signo esperado pre-registrado: -1 (contrarian)")
    daily = df_rel.groupby("date").agg(
        mean_rel=("rel", "mean"), sentiment=("sentiment_v1", "first"), n=("symbol", "nunique")
    )
    daily = daily[(daily["n"] >= MIN_SYMBOLS) & daily["sentiment"].notna()].sort_index()
    n_sig_b = 0
    for name, (start, end) in WINDOWS.items():
        wdf = daily[(daily.index >= start) & (daily.index <= end)]
        x, y = wdf["sentiment"].to_numpy(), wdf["mean_rel"].to_numpy()
        L = min(12, len(x) // 8)
        rho, _ = stats.spearmanr(x, y)
        # t de la pendiente rank: OLS de y sobre ranks(x), SE HAC (Newey-West).
        rx = stats.rankdata(x)
        X = np.column_stack([np.ones_like(rx), rx])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        e = y - X @ beta
        k = 2
        n = len(y)
        meat = np.zeros((k, k))
        for t in range(n):
            xt = X[t][:, None]
            meat += (e[t] ** 2) * (xt @ xt.T)
        for j in range(1, min(L, n - 1) + 1):
            w = 1.0 - j / (L + 1.0)
            G = np.zeros((k, k))
            for t in range(j, n):
                G += np.outer(X[t] * e[t], X[t - j] * e[t - j])
            meat += w * (G + G.T)
        inv = np.linalg.inv(X.T @ X)
        V = inv @ meat @ inv * (n / (n - k))
        t = float(beta[1] / np.sqrt(max(V[1, 1], 0.0))) if V[1, 1] > 0 else 0.0
        signo = "+" if t > 0 else "-"
        sig = "SIG" if abs(t) > THRESHOLD and t < 0 else "no"
        n_sig_b += int(sig == "SIG")
        out(f"{'AAII_timing':18s} {name:7s} {n:6d} {rho:+9.4f} {np.sqrt(V[1,1]):8.4f} "
            f"{t:+7.2f} {L:3d} {signo:>5s} {sig:>5s}")
    out(f"{'':18s} -> CUMPLE(AAII) si >=2/3 con signo -: {'SI' if n_sig_b >= 2 else 'no'} ({n_sig_b}/3)")

    cumple = "ver arriba por factor — criterio >=2/3 ventanas por test"
    out(f"\nCriterio: |t| > {THRESHOLD:.2f} con signo pre-registrado en >=2/3 ventanas. {cumple}")
    out(f"Out: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
