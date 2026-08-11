"""
PLAN_MEJORA_MATEMATICA §4.2 / Fase 0.5b (2026-08-11) — RMT Marchenko-Pastur.

Sonda directa de estructura cross-sectional real (no depende del IC):
  Matriz N×T de retornos estandarizados por ventana rodante (252d), q = N/T.
  λ₊ = (1+√q)² — autovalores sobre el umbral = factores reales, el resto
  ruido (Marchenko-Pastur).

Caveat de diseño (§4.2): el factor de mercado (autovalor enorme) se SACA
antes de aplicar MP: PCA sobre la matriz de correlación, se proyectan los
retornos sobre el primer componente (mercado), y MP se aplica a los
RESIDUOS. Si no, el autovalor del mercado contamina el conteo.

Criterio pre-registrado (gate §4.5):
  - 3-6 factores idiosincráticos sobre el umbral, con uno dominante ->
    plano de selección CHICO (el mercado explica casi todo) -> W2.
  - 3-6 factores REALES varios (ninguno dominante) -> estructura
    cross-sectional amplia -> consistente con W3.
  No decide solo: gate conjunto con 0.5a (rr2) y 0.5c (ridge).
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
WINDOW = 252          # estandarización rodante
MIN_COMMON = 180      # mínimo de fechas comunes para incluir un símbolo


def main():
    out_path = os.path.join("data", "cache", f"rmt_mp_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    out("=" * 72)
    out("FASE 0.5b (§4.2) — RMT / Marchenko-Pastur, factor de mercado removido")
    out(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END}")
    out(f"Estandarización rodante: {WINDOW}d | min fechas comunes: {MIN_COMMON}")
    out("=" * 72)

    print("Cargando precios...", flush=True)
    price_data = load_universe(SYMBOLS, START, END)
    out(f"precios cargados: {len(price_data)} símbolos")

    # Matriz de retornos diarios alineada por fecha
    closes = pd.DataFrame({s: df["close"] for s, df in price_data.items()})
    closes = closes.sort_index().ffill().dropna()
    rets = closes.pct_change().dropna(how="all")
    rets = rets[rets.index >= pd.Timestamp("2020-01-01")]  # mismo arranque que W1
    rets = rets.dropna(axis=1, thresh=MIN_COMMON)
    rets = rets.dropna()
    T, N = rets.shape
    out(f"Matriz: N={N} símbolos x T={T} días (q=N/T={N / T:.4f})")

    # Estandarización rodante: z = (r - mean_roll)/std_roll
    z = (rets - rets.rolling(WINDOW, min_periods=60).mean()) / rets.rolling(
        WINDOW, min_periods=60).std()
    z = z.dropna()
    T2, N2 = z.shape
    out(f"Tras estandarización rodante (dropna): N={N2} x T={T2}")

    q = N2 / T2
    lam_plus = (1 + np.sqrt(q)) ** 2
    out(f"q={q:.4f} | λ₊ (umbral MP) = {(1 + np.sqrt(q)) ** 2:.3f}")

    # ---- PASO 1: espectro de la matriz de correlación COMPLETA (con mercado) ----
    corr = np.corrcoef(z.values.T)
    eigs_full = np.linalg.eigvalsh(corr)
    eigs_full = eigs_full[::-1]
    n_above_full = int(np.sum(eigs_full > lam_plus))
    out(f"\n--- Espectro completo (con mercado) ---")
    out(f"  λ_max={eigs_full[0]:.3f} | λ₂={eigs_full[1]:.3f} | λ₃={eigs_full[2]:.3f}")
    out(f"  autovalores sobre λ₊={lam_plus:.3f}: {n_above_full}")

    # ---- PASO 2: remover el factor de mercado (PCA, 1er componente) ----
    eigvals_res_full, eigvecs_full = np.linalg.eigh(corr)
    pc1 = eigvecs_full[:, -1]                     # autovector del λ más grande
    scores = z.values @ pc1                       # proyección (factor de mercado)
    beta = (z.values.T @ scores) / (scores @ scores)  # regresión por símbolo
    resid = z.values - np.outer(scores, beta)     # residuos sin mercado
    corr_res = np.corrcoef(resid.T)
    eigs_res = np.linalg.eigvalsh(corr_res)[::-1]
    n_above_res = int(np.sum(eigs_res > lam_plus))
    pct_var = eigs_full[0] / eigs_full.sum()
    out(f"\n--- Espectro RESIDUAL (mercado removido, §4.2) ---")
    out(f"  varianza explicada por PC1 (mercado): {pct_var:.1%}")
    out(f"  λ_max_res={eigs_res[0]:.3f} | λ₂={eigs_res[1]:.3f} | λ₃={eigs_res[2]:.3f} | λ₄={eigs_res[3]:.3f}")
    out(f"  autovalores residuales sobre λ₊={lam_plus:.3f}: {n_above_res}")
    if n_above_res > 0:
        top = ", ".join(f"λ={e:.2f}" for e in eigs_res[:n_above_res])
        out(f"  [ {top} ]")
    share_top = eigs_res[0] / eigs_res.sum() if N2 > 1 else 0.0
    out(f"  dominancia 1er factor residual: {share_top:.1%} de la varianza residual")

    out("\n--- INTERPRETACIÓN (§4.2/§4.5) ---")
    if n_above_res <= 1:
        out("  0-1 factor residual -> casi toda la estructura es mercado (o ruido).")
        out("  Plano de selección idiosincrático CHICO -> consistente con W2.")
    elif n_above_res <= 6 and share_top > 0.4:
        out("  Pocos factores con uno dominante -> plano de selección chico -> W2.")
    else:
        out("  Estructura residual real amplia -> consistente con W3.")
    out("  (Veredicto conjunto: 0.5a rr2 + 0.5b RMT + 0.5c ridge — este script solo informa)")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
