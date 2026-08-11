"""
PLAN_MEJORA_MATEMATICA §9 / Rama W2, opción (c) — Diagnóstico sectorial previo
(2026-08-11, pre-registrado ANTES de correr).

Pregunta: ¿hay estructura cross-sectional a nivel SECTOR/CLUSTER explotable?
La opción (c) de la rama W2 (rotación sectorial) NO puede tocarse con un trial
de motor hasta tener evidencia propia del plano sectorial — este script la
produce, con el mismo protocolo que 0.5a (rank IC intra-día + Newey-West).

RESTRICCIONES PRE-REGISTRADAS (fijadas por el usuario):
  1. Clusters definidos ENDÓGENAMENTE a partir de los autovectores residuales
     de RMT (los 8 > λ₊, cargas sobre símbolos) y/o clustering jerárquico sobre
     la misma matriz residual. PROHIBIDO GICS o taxonomía externa: sería fuente
     de datos nueva sin verificar, con riesgo de lookahead de membership
     point-in-time (mismo vector de bug que §3.1).
  2. Corrección de multiple testing BONFERRONI sobre 8 clusters (no 4 como
     0.5a): umbral nominal |t| > z(1 - 0.025/8) ≈ 2.74 (vs 2.50 de 0.5a).

Método:
  A. Matriz residual idéntica a `rmt_mp_20260811_150849.txt` (N=50, T=1599,
     estandarización rodante 252d, mercado removido por PCA/PC1). Clusters:
     (a) autovectores: por cada factor > λ₊, símbolos con |carga| > 2/√N≈0.283;
     asignación hard por argmax|carga|. (b) clustering jerárquico Ward sobre
     distancia 1-|corr_res|, k = #factores > λ₊ (=8).
  B. Rank IC intra-día por cluster: por fecha, score_cluster = media del
     momentum_score de sus miembros (el factor que el motor ya usa); retorno
     fwd del cluster = media de fwd_return_20d de miembros; Spearman por fecha,
     promedio sobre fechas con SE Newey-West (L=4). Panel: TODAS las filas con
     fwd notna (la pregunta es de estructura de retornos, no de operabilidad);
     cluster requiere >= 3 símbolos en esa fecha.
  C. Significativo (|t| > 2.74, signo positivo) -> estructura sectorial
     explotable con momentum de cluster -> opción (c) viable para re-evaluación.
     No significativo -> la rotación por cluster no rescata -> (a) basket único
     queda como candidata por defecto.

Caveat pre-registrado: clusters estáticos (ventana completa, como en RMT). El
diagnóstico sólo prueba EXISTENCIA de estructura; un uso operacional exigiría
clusters rolling — eso se decide después si (c) llega a trial.
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE
from scripts.diagnose_rmt_mp import SYMBOLS, START, END, WINDOW

MIN_COMMON = 180
L = 4                     # lags Newey-West (mismo que 0.5a)
BONFERRONI_K = 8          # clusters testeados
UMBRAL_T = stats.norm.ppf(1 - 0.025 / BONFERRONI_K)   # ≈ 2.74
LOADING_THRESHOLD = 2.0 / np.sqrt(50)                 # ≈ 0.283
MIN_SYMBOLS_CLUSTER = 3


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet — corre build_factor_panel.py")
    return files[-1]


def residual_matrix():
    """Replica exacta del pipeline auditado de diagnose_rmt_mp.py."""
    price_data = load_universe(SYMBOLS, START, END)
    closes = pd.DataFrame({s: df["close"] for s, df in price_data.items()})
    closes = closes.sort_index().ffill().dropna()
    rets = closes.pct_change().dropna(how="all")
    rets = rets[rets.index >= pd.Timestamp("2020-01-01")]
    rets = rets.dropna(axis=1, thresh=MIN_COMMON).dropna()
    z = (rets - rets.rolling(WINDOW, min_periods=60).mean()) / rets.rolling(
        WINDOW, min_periods=60).std()
    z = z.dropna()
    corr = np.corrcoef(z.values.T)
    eigvals, eigvecs = np.linalg.eigh(corr)
    pc1 = eigvecs[:, -1]
    scores = z.values @ pc1
    beta = (z.values.T @ scores) / (scores @ scores)
    resid = z.values - np.outer(scores, beta)
    # OJO (fix 2026-08-11): los clusters DEBEN salir de los autovectores
    # RESIDUALES (la matriz con el mercado removido) — el conteo de 8 de
    # `rmt_mp_20260811_150849.txt` es sobre corr_res, no sobre corr completa.
    corr_res = np.corrcoef(resid.T)
    eigvals_res, eigvecs_res = np.linalg.eigh(corr_res)
    return (z, corr_res, eigvals_res[::-1], eigvecs_res[:, ::-1], 2, rets)


def newey_west_se(z: np.ndarray, lags: int) -> float:
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


def intraday_cluster_rank_ic(panel: pd.DataFrame, cluster_map: dict) -> dict:
    """Rank IC intra-día: score del cluster = media momentum_score de miembros;
    fwd = media fwd_return_20d. Spearman por fecha, promedio + SE Newey-West."""
    daily = []
    sym_to_cluster = {s: c for c, syms in cluster_map.items() for s in syms}
    panel = panel[panel["symbol"].isin(sym_to_cluster)].copy()
    panel["cluster"] = panel["symbol"].map(sym_to_cluster)
    for date, day in panel.groupby("date"):
        if day["cluster"].nunique() < 2:
            continue
        g = day.groupby("cluster").agg(
            score=("momentum_score", "mean"),
            fwd=("fwd_return_20d", "mean"),
            n=("symbol", "count"),
        ).dropna()
        g = g[g["n"] >= MIN_SYMBOLS_CLUSTER]
        if len(g) < 2:
            continue
        rho, _ = stats.spearmanr(g["score"], g["fwd"])
        if np.isfinite(rho):
            daily.append(rho)
    ics = np.array(daily)
    if len(ics) == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan,
                "significant": False, "n_clusters": 0}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, L)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(len(ics)), "mean_ic": mean_ic, "se_nw": se_nw, "t": t,
            "significant": bool(abs(t) > UMBRAL_T and mean_ic > 0),
            "n_clusters": len(cluster_map)}


def main():
    panel_path = latest_panel()
    out_path = os.path.join("data", "cache", f"sector_clusters_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    out("=" * 72)
    out("FASE §9(c) — Diagnóstico sectorial ENDÓGENO (pre-registrado)")
    out(f"Umbral Bonferroni 8 clusters: |t| > {UMBRAL_T:.2f} | carga > {LOADING_THRESHOLD:.3f}")
    out(f"Panel: {os.path.basename(panel_path)} | min símbolos/cluster: {MIN_SYMBOLS_CLUSTER}")
    out("=" * 72)

    print("Cargando precios y matriz residual (pipeline RMT auditado)...", flush=True)
    z, corr_res, eigs, eigvecs, _, _ = residual_matrix()
    q = z.shape[1] / z.shape[0]
    lam_plus = (1 + np.sqrt(q)) ** 2
    n_factors = int(np.sum(eigs > lam_plus))
    out(f"Matriz residual: N={z.shape[1]} x T={z.shape[0]} | λ₊={lam_plus:.3f} | "
        f"factores > λ₊: {n_factors}")

    symbols = list(z.columns)
    out(f"\nCargas |carga| > {LOADING_THRESHOLD:.3f} por factor (autovectores residuales):")
    for i in range(n_factors):
        loads = eigvecs[:, i]
        strong = [(s, float(abs(loads[j]))) for j, s in enumerate(symbols)
                  if abs(loads[j]) > LOADING_THRESHOLD]
        strong.sort(key=lambda x: -x[1])
        names = ", ".join(f"{s}({v:.2f})" for s, v in strong[:8])
        out(f"  F{i}: [ {names} ]")

    # ---- Clusters vía autovectores: asignación hard por argmax|carga| ----
    hard = {}
    for j, s in enumerate(symbols):
        best = int(np.argmax(np.abs(eigvecs[j, :n_factors])))
        hard.setdefault(best, []).append(s)
    out(f"\n--- Clusters por argmax|carga| sobre {n_factors} factores ---")
    for c in sorted(hard):
        out(f"  C{c}: n={len(hard[c]):2d} | {', '.join(hard[c][:12])}")

    # ---- Clusters vía jerárquico Ward sobre 1-|corr_res|, k = n_factors ----
    dist = 1.0 - np.abs(corr_res)
    np.fill_diagonal(dist, 0.0)
    hc_link = linkage(squareform(dist, checks=False), method="ward")
    hc_labels = fcluster(hc_link, t=n_factors, criterion="maxclust")
    hc = {}
    for lbl, s in zip(hc_labels, symbols):
        hc.setdefault(int(lbl), []).append(s)
    out(f"\n--- Clusters jerárquicos Ward, k={n_factors} ---")
    for c in sorted(hc):
        out(f"  H{c}: n={len(hc[c]):2d} | {', '.join(hc[c][:12])}")

    panel = pd.read_parquet(panel_path)
    panel = panel[panel["fwd_return_20d"].notna()].sort_values("date")

    out(f"\n--- Rank IC intra-día por cluster (protocolo 0.5a, Bonferroni {BONFERRONI_K}) ---")
    out(f"{'clusters':22s} {'n_días':>6s} {'mean_IC':>8s} {'SE_NW':>7s} {'t':>7s} {'veredicto':>14s}")
    results = {}
    for name, cmap in [("autovectores", hard), ("jerárquico", hc)]:
        r = intraday_cluster_rank_ic(panel, cmap)
        results[name] = r
        v = "SIGNIFICATIVO (c viable)" if r["significant"] else f"no sig (umbral {UMBRAL_T:.2f})"
        out(f"{name:22s} {r['n_days']:6d} {r['mean_ic']:+8.4f} {r['se_nw']:7.4f} "
            f"{r['t']:+7.2f} {v:>14s}")

    out("\n--- INTERPRETACIÓN (§9.c) ---")
    sig = [k for k, r in results.items() if r["significant"]]
    if sig:
        out("  Estructura sectorial explotable: al menos una definición de cluster")
        out("  da rank IC intra-día significativo (Bonferroni 8) con momentum medio.")
        out("  -> opción (c) rotación sectorial pasa a candidata con evidencia.")
    else:
        out("  Ninguna definición de cluster da rank IC intra-día significativo.")
        out("  -> la rotación por momentum de cluster no rescata la selección;")
        out("     opción (a) basket único queda como candidata por defecto.")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())