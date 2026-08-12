"""
PLAN_MEJORA_MATEMATICA §14 — rank IC intra-día por SUB-PERÍODO (2026-08-12).
PRE-REGISTRADO antes de correr.

Motivo: nunca se testeó si momentum/RSI/ADX tuvieron un quiebre de régimen en el
tiempo — todo §0.5a corrió sobre la muestra completa 2019-2026 de una sola vez.
Motivado por evidencia externa verificada (NY Fed, "The Overnight Drift" / "The
Disappearing Overnight Drift"): una anomalía real y documentada académicamente
(retorno 2-3am ET ligado a apertura europea) se desvaneció desde 2021 por
compresión de la dispersión de desequilibrios de cierre — prueba de que
anomalías reales pueden dejar de funcionar con el tiempo. Pregunta: ¿algo similar
le pasó a nuestros propios factores?

Metodología (idéntica a diagnose_rr2_intraday.py — rank IC intra-día, Newey-West,
NO pooled — mismo error que se corrigió en §4.1), partida en 2 sub-períodos fijados
ANTES de mirar resultados:
  PRE  = fechas < 2022-01-01 (2019-2021, ~3 años)
  POST = fechas >= 2022-01-01 (2022-2026, ~4.5 años)
El corte en 2022 replica el punto de quiebre documentado en la literatura externa
verificada (post-2021), no se eligió mirando nuestros propios datos.

Criterio pre-registrado (sin conocer el resultado): se testean 4 factores x 2
sub-períodos = 8 hipótesis -> Bonferroni-8, umbral |t| > 2.74 (two-sided, alpha
familiar 0.05/8). "Quiebre de régimen" = significativo en un sub-período con signo
esperado y NO significativo (o signo contrario) en el otro, ambos bajo el umbral
corregido. Si ningún factor cruza el umbral en NINGÚN sub-período, no hay evidencia
de quiebre temporal (ni de señal, en ningún período).

El script NO decide nada por sí mismo más que aplicar este criterio mecánicamente.
Ver regla §3.4: todo número se verifica contra el artefacto.
"""
import datetime
import glob
import math
import os

import numpy as np
import pandas as pd
from scipy import stats

FACTORS = {
    "momentum_score": +1,
    "rsi_score": +1,
    "trend_score": +1,
    "adx_score": +1,
}
TARGET = "fwd_return_20d"
HORIZON = 20
STRIDE_DAYS = 5
MIN_SYMBOLS = 5
L = int(np.ceil(HORIZON / STRIDE_DAYS))
CORTE = "2022-01-01"
N_TESTS = 8  # 4 factores x 2 sub-periodos
ALPHA_FAMILIAR = 0.05
Z_BONFERRONI = float(stats.norm.ppf(1 - (ALPHA_FAMILIAR / N_TESTS) / 2))


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    n = len(z)
    if n < 3:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    lag_max = min(lags, n - 2)
    if lag_max < 1:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (lags + 1)
    denom = 1 + 2 * np.sum(w * rho)
    n_eff = n / max(denom, 1.0)
    return float(np.std(z, ddof=1) / np.sqrt(n_eff))


def intraday_rank_ic(panel: pd.DataFrame, factor: str) -> dict:
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
        return {"n_days": 0, "mean_ic": float("nan"), "se_nw": float("nan"), "t": float("nan")}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, L)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(n_days), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def main():
    path = latest_panel()
    out_path = os.path.join("data", "cache",
                            f"rr2_subperiodos_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    panel = pd.read_parquet(path)
    df = panel[panel["eligible"] & panel[TARGET].notna()].copy()
    df["date"] = pd.to_datetime(df["date"])

    log("=" * 72)
    log("§14 — rank IC intra-día por SUB-PERÍODO — PRE-REGISTRADO")
    log(f"Panel: {os.path.basename(path)} | corte: {CORTE} (fijado por literatura externa, no por los datos)")
    log(f"Bonferroni-{N_TESTS} (4 factores x 2 sub-períodos) | umbral |t| > {Z_BONFERRONI:.2f}")
    log("=" * 72)

    pre = df[df["date"] < pd.Timestamp(CORTE)]
    post = df[df["date"] >= pd.Timestamp(CORTE)]
    log(f"\nPRE  ({df['date'].min().date()} -> {pd.Timestamp(CORTE).date()}): "
        f"{pre['date'].nunique()} fechas, {len(pre)} filas elegibles")
    log(f"POST ({pd.Timestamp(CORTE).date()} -> {df['date'].max().date()}): "
        f"{post['date'].nunique()} fechas, {len(post)} filas elegibles")

    log(f"\n{'factor':16s} {'periodo':6s} {'n_days':>7s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'sig(Bonf)':>10s}")
    resultados = {}
    for factor, sign in FACTORS.items():
        for periodo, sub in [("PRE", pre), ("POST", post)]:
            res = intraday_rank_ic(sub, factor)
            sig = (not math.isnan(res["t"])) and abs(res["t"]) > Z_BONFERRONI and np.sign(res["mean_ic"]) == sign
            resultados[(factor, periodo)] = {**res, "sig": sig}
            log(f"{factor:16s} {periodo:6s} {res['n_days']:7d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {str(sig):>10s}")

    log("\n--- VEREDICTO (§14, pre-registrado) ---")
    any_break = False
    any_sig_anywhere = False
    for factor in FACTORS:
        pre_r = resultados[(factor, "PRE")]
        post_r = resultados[(factor, "POST")]
        if pre_r["sig"] or post_r["sig"]:
            any_sig_anywhere = True
        quiebre = pre_r["sig"] != post_r["sig"]
        if quiebre:
            any_break = True
            ganador = "PRE" if pre_r["sig"] else "POST"
            log(f"  {factor}: QUIEBRE DE RÉGIMEN — significativo sólo en {ganador} "
                f"(PRE t={pre_r['t']:+.2f}, POST t={post_r['t']:+.2f})")
        else:
            log(f"  {factor}: sin quiebre (PRE t={pre_r['t']:+.2f}, POST t={post_r['t']:+.2f}, "
                f"ambos {'sig' if pre_r['sig'] else 'no sig'})")

    if not any_sig_anywhere:
        log("\n=> Ningún factor es significativo en NINGÚN sub-período (Bonferroni-8). "
            "No hay evidencia de quiebre temporal porque no hay señal en ningún momento.")
    elif any_break:
        log("\n=> Al menos un factor muestra quiebre de régimen real.")
    else:
        log("\n=> Los factores significativos (si los hay) lo son de forma consistente en ambos "
            "períodos, o ninguno lo es en ninguno — sin evidencia de quiebre.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
