"""
PLAN_MEJORA_MATEMATICA §25 (2026-08-17) — Tarea B: ADX walk-forward (Cline).

Test pre-registrado (ver PLAN_MEJORA_MATEMATICA.md §25, escrito ANTES de correr):

1. TEST PRINCIPAL (decide): rank IC intra-dia de adx_score contra fwd_return_20d,
   por ventana W1/W2/W3 — Spearman por fecha + SE Newey-West, L = min(12, n_dias//8).
   Criterio: |t| > 2.77 (Bonferroni-9 bilateral) con signo +1 en >=2/3 ventanas.
2. CHEQUE DE FIDELIDAD: el rank IC TOTAL (L=4) debe reproducir §0.5a
   (rr2_intraday_20260811_150741.txt): mean_IC +0.0679, t +2.31. Si falla -> aborta
   sin interpretar (exit 2).
3. TEST SECUNDARIO (contexto, nunca hallazgo): premia operativa ADX alto (score 0.9)
   vs ADX bajo (score 0.3) dentro de la poblacion elegible.

Reglas del proyecto aplicadas:
- Python 3.9 real (backend/.venv).
- NO toca el motor ni signal_engine.py: lee el panel ya construido.
- Las ventanas, el umbral y el signo esperado estan pre-registrados en §25.
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

FACTOR = "adx_score"
TARGET = "fwd_return_20d"
HORIZON = 20
STRIDE_DAYS = 5
MIN_SYMBOLS = 5
L_TOTAL_FIDELITY = int(np.ceil(HORIZON / STRIDE_DAYS))  # 4 = identico a §0.5a

# Fidelidad §0.5a (artefacto rr2_intraday_20260811_150741.txt)
REF_MEAN_IC = 0.0679
REF_T = 2.31
TOL_MEAN_IC = 0.001
TOL_T = 0.05

# Umbral pre-registrado §25: Bonferroni-9 bilateral -> z = ppf(1 - 0.05/18) ~ 2.77
ALPHA_PER = 0.05 / 18.0
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))

WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet — corre build_factor_panel.py")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusto Newey-West (pesos Bartlett) — copia fiel de la de §0.5a."""
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


def collect_daily_ics(df: pd.DataFrame) -> np.ndarray:
    """ICS diarios (Spearman por fecha) — pre-pasada para conocer n_dias usado.

    La significancia viene de la distribucion temporal de los ICs diarios
    (n fechas), no del n por fecha (nota de diseno de §0.5a).
    """
    ics = []
    for _date, day in df.groupby("date"):
        day = day[day[FACTOR].notna() & day[TARGET].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day[FACTOR], day[TARGET])
        if np.isfinite(rho):
            ics.append(rho)
    return np.array(ics)


def rank_ic_stats(ics: np.ndarray, lags: int) -> dict:
    """Media, SE Newey-West y t de la serie de ICs diarios, con el L ya fijado.

    L se fija por ventana segun la regla de §23: L = min(12, floor(n_dias/8)),
    donde n_dias es el total de ICs USADOS (no las fechas brutas del panel).
    """
    n = len(ics)
    if n == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(n), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}



def operational_context(df: pd.DataFrame) -> dict:
    """Premia ADX alto (score 0.9 = adx14>25) vs ADX bajo (0.3 = adx14 en [20,25]).

    Contexto operativo — el veredicto lo da SOLO el rank IC pre-registrado.
    """
    high = df[df[FACTOR] > 0.5]
    low = df[df[FACTOR] <= 0.5]
    n_h, n_l = int(len(high)), int(len(low))
    if n_h == 0 or n_l == 0:
        return {
            "n_high": n_h, "n_low": n_l, "premia": np.nan, "t_pooled": np.nan,
            "vpp_high": np.nan, "vpp_low": np.nan,
        }
    h_m, h_v = high[TARGET].mean(), high[TARGET].var(ddof=1)
    l_m, l_v = low[TARGET].mean(), low[TARGET].var(ddof=1)
    premia = float(h_m - l_m)
    sp2 = ((n_h - 1) * h_v + (n_l - 1) * l_v) / (n_h + n_l - 2)
    se = np.sqrt(sp2 * (1.0 / n_h + 1.0 / n_l))
    t = premia / se if (se > 0 and np.isfinite(se)) else np.nan
    return {
        "n_high": n_h, "n_low": n_l, "premia": premia, "t_pooled": float(t),
        "vpp_high": float((high[TARGET] > 0).mean()),
        "vpp_low": float((low[TARGET] > 0).mean()),
    }


def main() -> int:
    panel_path = latest_panel()
    out_path = os.path.join(
        "data", "cache", f"trial_adx_walkforward_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    panel = pd.read_parquet(panel_path)
    df = panel[panel["eligible"] & panel[TARGET].notna()].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §25 — Tarea B: ADX walk-forward (Cline, 2026-08-17)")
    out(f"Panel: {os.path.basename(panel_path)} | filas eligible+target: {len(df)}")
    out(f"Factor: {FACTOR} (dicotomico 0.3/0.9, motor compute_factor_frame) | Target: {TARGET}")
    out(f"MIN_SYMBOLS: {MIN_SYMBOLS} | L por ventana: min(12, n_dias//8) | L TOTAL (fid): {L_TOTAL_FIDELITY}")
    out(f"Umbral pre-registrado: |t| > {THRESHOLD:.3f} (Bonferroni-9 bilateral) con signo +1 en >=2/3 ventanas")
    out("=" * 78)


    # --- Cheque de fidelidad §0.5a (TOTAL, L=4) ---
    fid = rank_ic_stats(collect_daily_ics(df), L_TOTAL_FIDELITY)
    out("\n--- CHEQUE DE FIDELIDAD contra §0.5a (TOTAL 2019-2026, L=4) ---")
    out(f"  medido: mean_IC={fid['mean_ic']:+.4f}  t={fid['t']:+.2f}  n_dias={fid['n_days']}")
    out(f"  §0.5a:  mean_IC={REF_MEAN_IC:+.4f}  t={REF_T:+.2f}")
    ok_ic = abs(fid["mean_ic"] - REF_MEAN_IC) <= TOL_MEAN_IC
    ok_t = abs(fid["t"] - REF_T) <= TOL_T
    if not (ok_ic and ok_t):
        out(f"  FALLO: |mean_IC-{REF_MEAN_IC}|>{TOL_MEAN_IC} o |t-{REF_T}|>{TOL_T}")
        out("  -> ABORTA sin interpretar (regla §14: panel con flujo roto no decide nada)")
        return 2
    out("  OK: reproduccion dentro de tolerancia -> la reimplementacion es la misma evidencia")

    # --- Test principal: rank IC por ventana ---
    out("\n--- TEST PRINCIPAL (pre-registrado §25): rank IC intra-dia por ventana ---")
    out(f"{'ventana':7s} {'rango':22s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s} {'signo':>5s} {'|t|>2.77':>9s}")
    results = {}
    for name, (start, end) in WINDOWS.items():
        wdf = df[(df["date"] >= start) & (df["date"] <= end)]
        ics_w = collect_daily_ics(wdf)
        L = min(12, len(ics_w) // 8)
        res = rank_ic_stats(ics_w, L)
        results[name] = res
        signo = "+" if (np.isfinite(res["t"]) and res["t"] > 0) else "-"
        cross = "SIG" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and signo == "+") else "no"
        rango = f"{start.date()} -> {end.date()}"
        out(f"{name:7s} {rango:22s} {res['n_days']:6d} {res['mean_ic']:+9.4f} "
            f"{res['se_nw']:8.4f} {res['t']:+7.2f} {L:3d} {signo:>5s} {cross:>9s}")

    ics_total = collect_daily_ics(df)
    res_total = rank_ic_stats(ics_total, min(12, len(ics_total) // 8))
    out(f"TOTAL (ref) 2019-01-02 -> 2026-07-06 {res_total['n_days']:6d} "
        f"{res_total['mean_ic']:+9.4f} {res_total['se_nw']:8.4f} {res_total['t']:+7.2f}")

    n_sig = sum(
        1 for r in results.values()
        if np.isfinite(r["t"]) and abs(r["t"]) > THRESHOLD and r["t"] > 0
    )
    cumple = n_sig >= 2
    out(f"\nCriterio pre-registrado: |t| > {THRESHOLD:.2f} con signo +1 en >=2/3 ventanas -> ventanas SIG: {n_sig}/3")
    out(f"VEREDICTO: {'CUMPLE' if cumple else 'NO_CUMPLE'}")

    # --- Test secundario: contexto operativo ---
    out("\n--- TEST SECUNDARIO (contexto, NUNCA hallazgo): premia ADX alto(0.9) vs bajo(0.3) ---")
    out(f"{'ventana':7s} {'n_alto':>6s} {'n_bajo':>6s} {'premia':>9s} {'t_pooled':>9s} {'vpp_alto':>9s} {'vpp_bajo':>9s}")
    for name, (start, end) in WINDOWS.items():
        wdf = df[(df["date"] >= start) & (df["date"] <= end)]
        ctx = operational_context(wdf)
        out(f"{name:7s} {ctx['n_high']:6d} {ctx['n_low']:6d} {ctx['premia']:+9.5f} "
            f"{ctx['t_pooled']:+9.2f} {ctx['vpp_high']:9.3f} {ctx['vpp_low']:9.3f}")
    out("  Reserva pre-registrada: filas solapadas temporalmente (stride 5d, horizonte 20d) —")
    out("  el t_pooled es contexto; el veredicto lo da SOLO el rank IC.")

    out(f"\nOut: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
