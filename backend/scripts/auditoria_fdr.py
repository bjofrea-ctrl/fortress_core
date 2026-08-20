"""Auditoría FDR (Benjamini-Hochberg) sobre todos los factores cerrados del proyecto.

AUDITORÍA / DIAGNÓSTICO — NO es un trial nuevo:
  - Solo lectura de artefactos existentes (t-stats por ventana ya calculados).
  - NO consume n_trials del ledger, NO toca mercado ni datos, NO corre backtests.
  - NO integra nada al motor ni cambia estados del ledger.

MÉTODO DE POOLING (decidido ANTES de correr, no después de ver números):
  Meta-análisis de Stouffer (z ponderado por varianza inversa):
      z_pool = sum(w_i * t_i) / sqrt(sum(w_i^2)),  w_i = sqrt(n_i)
  - Direccional: conserva el signo del efecto y cancela evidencia opuesta entre
    ventanas. Cada factor tiene hipótesis direccional pre-registrada; Fisher (no
    direccional) combinaría p's bilaterales y crearía discoveries espurios cuando
    una ventana es fuerte y otra opuesta (p.ej. AAII W2=+2.94 con W1=-0.32).
  - Pesos sqrt(n) = varianza inversa (SE_NW ~ 1/sqrt(n)), consistente con el
    pooling "TOTAL" que el proyecto ya usa (ADX ref t=+2.31 sobre n=151).
  - p bilateral a partir del z_pool (gaussiana).

PROCEDIMIENTO BH (Benjamini-Hochberg):
  p_(1)<=...<=p_(m); rechazar las k mas chicas con p_(k) <= q*k/m.
  Se reporta q=0.05 Y q=0.10 (ambos, no se elige el que convenga).

FUENTES (t-stats verificados contra artefactos reales en data/cache/):
  - ADX daily ........ trial_adx_walkforward_20260817_103916.txt (§25)
  - mom/rsi/adx rel .. trial_xsec_relative_20260817_184355.txt (§28)
  - AAII timing ...... trial_xsec_relative_20260817_184355.txt (§28)
  - mom/rsi/adx TB ... retest_triple_barrier_20260816_091649.txt (§23)
  - mom/rsi/adx week . weekly_indicators_20260817_105918.txt (§26)
  - FinBERT .......... trial_finbert_eventstudy_20260817_163512.txt (§27)
  - C6 hedged ........ backtest_c6_hedge_costo_medido_20260819_155509.txt (§34)
  - Donchian ......... diagnose_donchian_intraday_20260812_201008.txt (§17)
  - gap-reversion .... backtest_gap_costs_20260812_173951.txt (§13.1, bruto)

EXCLUIDOS del set BH (se reportan por separado, con justificación):
  - EVT stops: trial declarado INVALIDO por diseño (nunca midio un efecto:
    el sizing EVT nunca fue binding). Sin t por ventana, solo DSR.
  - lead-lag: familia de 50 tests de correlacion cruzada, sin un t unico.
  - MA200 clusters §16: mismo senal subyacente que C6-hedged; su afirmacion era
    heterogeneidad de clusters (REFUTADA: mismo signo en todos), no un factor.
"""

from __future__ import annotations

import json
import math
from datetime import datetime

OUT_CACHE = "data/cache/auditoria_fdr_{ts}.txt"


def two_sided_p(z: float) -> float:
    """p bilateral gaussiana a partir del z (normal CDF via erfc)."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def stouffer(windowed):
    """Stouffer weighted-z (pesos sqrt(n)) sobre [(t, n), ...] -> (z_pool, p)."""
    if not windowed:
        raise ValueError("necesita al menos una ventana")
    num = 0.0
    den2 = 0.0
    for t, n in windowed:
        w = math.sqrt(n)
        num += w * t
        den2 += w * w
    z = num / math.sqrt(den2)
    return z, two_sided_p(z)


def bh(pvals, q):
    """Benjamini-Hochberg sobre lista de p. Devuelve set de indices rechazados."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    k_star = 0
    for k in range(1, m + 1):
        if pvals[order[k - 1]] <= q * k / m:
            k_star = k
    rejected = set(order[:k_star])
    return rejected, k_star


def fmt_p(p):
    if p < 1e-4:
        return f"{p:.2e}"
    return f"{p:.4f}"


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_CACHE.format(ts=ts)

    # ---- factores con t-stats por ventana: [(t, n), ...] por ventana W1/W2/W3 ----
    windowed = {
        # ADX daily (§25 / §28 = mismos datos)
        "ADX_daily":        [(0.79, 53), (1.54, 20), (1.47, 53)],
        # rank-IC relativo (§28)
        "momentum_daily":   [(-0.03, 60), (-1.01, 33), (-0.11, 64)],
        "rsi_daily":        [(0.76, 53), (-0.62, 25), (1.05, 59)],
        "AAII_timing":      [(-0.32, 60), (2.94, 33), (0.04, 64)],
        # triple barrier (§23)
        "momentum_TB":      [(-1.97, 54), (-1.71, 30), (0.00, 53)],
        "rsi_TB":           [(-0.96, 47), (1.73, 22), (0.31, 50)],
        "adx_TB":           [(-1.13, 47), (1.90, 19), (-0.08, 45)],
        # semanales (§26)
        "momentum_weekly":  [(-0.17, 157), (-0.01, 104), (0.19, 131)],
        "rsi_weekly":       [(-0.08, 157), (-0.44, 104), (0.14, 131)],
        "adx_weekly":       [(0.31, 157), (0.16, 104), (0.33, 131)],
        # FinBERT (§27) — ventanas E1/E2/E3
        "FinBERT":          [(0.38, 137), (-0.85, 113), (-0.08, 81)],
    }

    # ---- factores con UN t representativo (sin descomposicion por ventana) ----
    single = {
        # C6 MA200 hedged: LS-HEDGE bruto t-NW (senal, previo a costos) — §34
        "C6_hedged":   (1.07, 2666),
        # Donchian rank IC — §17
        "Donchian":    (-0.81, 187),
        # gap-reversion: fade bruto t-NW (senal a horizonte de la estrategia) — §13.1
        "gap_reversion": (-0.20, 2206),
    }

    # ---- armar set BH (m = numero real de factores) ----
    factors = []
    for name, wins in windowed.items():
        z, p = stouffer(wins)
        ns = [n for _, n in wins]
        factors.append({
            "name": name, "kind": "windowed", "z": z, "p": p,
            "windows": [t for t, _ in wins], "n": ns, "n_total": sum(ns),
        })
    for name, (t, n) in single.items():
        factors.append({
            "name": name, "kind": "single", "z": t, "p": two_sided_p(t),
            "windows": [t], "n": [n], "n_total": n,
        })

    m = len(factors)
    pvals = [f["p"] for f in factors]

    res05, k05 = bh(pvals, 0.05)
    res10, k10 = bh(pvals, 0.10)

    # ---- armar texto ----
    L = []
    L.append("=" * 80)
    L.append("AUDITORIA FDR (Benjamini-Hochberg) — todos los factores cerrados")
    L.append(f"Generado: {ts} | NO es trial nuevo, NO consume n_trials, solo lectura")
    L.append("Metodo de pooling (decidido ANTES de correr): Stouffer weighted-z")
    L.append("  z_pool = sum(sqrt(n_i)*t_i)/sqrt(sum(n_i)); p bilateral gaussiana")
    L.append("BH sobre m=%d factores (no ventanas), q=0.05 y q=0.10 (ambos)" % m)
    L.append("=" * 80)
    L.append("")
    L.append(f"{'factor':<18}{'t_pool':>9}{'p_pool':>12}{'n':>7}{'rank':>6}"
             f"{'corte05':>10}{'corte10':>10}  BH05  BH10  Bonf_orig")
    L.append("-" * 92)

    # BH devuelve indices en la lista ORIGINAL `factors`; mapear por nombre
    rej05_names = {factors[i]["name"] for i in res05}
    rej10_names = {factors[i]["name"] for i in res10}
    # orden por p ascendente
    ordered = sorted(factors, key=lambda f: f["p"])
    for r, f in enumerate(ordered, start=1):
        f["rank"] = r
        th05 = 0.05 * r / m
        th10 = 0.10 * r / m
        bh05 = "SI" if f["name"] in rej05_names else "no"
        bh10 = "SI" if f["name"] in rej10_names else "no"
        bonf = {
            "ADX_daily": "NO_CUMPLE",
            "momentum_daily": "NO_CUMPLE",
            "rsi_daily": "NO_CUMPLE",
            "AAII_timing": "NO_CUMPLE",
            "momentum_TB": "NO_CUMPLE",
            "rsi_TB": "NO_CUMPLE",
            "adx_TB": "NO_CUMPLE",
            "momentum_weekly": "NO_CUMPLE",
            "rsi_weekly": "NO_CUMPLE",
            "adx_weekly": "NO_CUMPLE",
            "FinBERT": "NO_CUMPLE",
            "C6_hedged": "NO_CUMPLE",
            "Donchian": "NO_CUMPLE",
            "gap_reversion": "NO_CUMPLE",
        }[f["name"]]
        L.append(f"{f['name']:<18}{f['z']:>+9.2f}{fmt_p(f['p']):>12}{f['n_total']:>7}"
                 f"{f['rank']:>6}{fmt_p(th05):>10}{fmt_p(th10):>10}  {bh05:>4}  {bh10:>4}  {bonf}")

    L.append("")
    L.append(f"Resultado BH q=0.05: k_rechazados = {k05}")
    L.append(f"Resultado BH q=0.10: k_rechazados = {k10}")
    L.append("")
    L.append("Nota corte BH(k): el k-esimo p mas chico debe ser <= q*k/m para ser rechazado.")
    L.append("")

    # ---- excluidos ----
    L.append("-" * 80)
    L.append("EXCLUIDOS del set BH (se reportan por separado, con justificacion):")
    L.append("  - EVT stops (§20): trial INVALIDO por diseno — el sizing EVT nunca fue")
    L.append("    binding (min() con Kelly); nunca midio un efecto. Solo DSR")
    L.append("    0.0649/0.0253/0.1602, sin t por ventana. No es candidato a discovery.")
    L.append("  - lead-lag (§22): familia de 50 tests de correlacion cruzada, sin un t")
    L.append("    unico. Ningun par cruzo Bonferroni-50 (|t|>3.29); max |t| ~ 2.69.")
    L.append("  - MA200 clusters (§16): mismo senal subyacente que C6_hedged; su")
    L.append("    afirmacion era heterogeneidad de clusters (REFUTADA: mismo signo en")
    L.append("    todos: C3 y C6 negativos). No es un factor direccional independiente.")
    L.append("")

    # ---- robustez de m ----
    m11 = [f for f in factors if f["kind"] == "windowed"]
    p11 = [f["p"] for f in m11]
    r05_11, k05_11 = bh(p11, 0.05)
    r10_11, k10_11 = bh(p11, 0.10)
    L.append("-" * 80)
    L.append("ROBUSTEZ de m: el set solo-windowed (m=%d, los 11 con pooling por ventana):"
             % len(m11))
    L.append(f"  BH q=0.05 -> k={k05_11} | BH q=0.10 -> k={k10_11}")
    L.append("  (agregar factores single-t solo sube m y ENDURECE el corte; el veredicto")
    L.append("   de 'sin discovery' es robusto al m elegido)")
    L.append("")

    L.append(f"Out: {out_path}")

    text = "\n".join(L) + "\n"
    with open(out_path, "w") as fh:
        fh.write(text)
    print(text)

    # JSON resumen para uso posterior / documento
    summary = {
        "timestamp": ts,
        "m": m,
        "metodo": "stouffer_weighted_z",
        "q05_rechazados": k05,
        "q10_rechazados": k10,
        "factores": [
            {"factor": f["name"], "t_pool": round(f["z"], 4),
             "p_pool": f["p"], "rank": f["rank"], "n": f["n_total"]}
            for f in ordered
        ],
    }
    with open(out_path.replace(".txt", ".json"), "w") as fh:
        json.dump(summary, fh, indent=2)


if __name__ == "__main__":
    main()
