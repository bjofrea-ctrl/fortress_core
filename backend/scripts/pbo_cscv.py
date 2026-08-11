"""
PLAN §11 Fase 3 — PBO / CSCV (Bailey & López de Prado 2015) sobre los trades
OOS del mejor estado conocido (trial #10, huella 20260810_165713).

CSCV clásico compara N configuraciones (selección de la mejor IS y su
degradación OOS). Con UNA configuración (la V1 actual), la formulación
honesta es el LOGIT DE ESTABILIDAD: en cada submuestra combinatoria,
logit = sharpe_test - sharpe_train de la MISMA configuración.
PBO = P(logit < 0): probabilidad de que el rendimiento fuera de muestra
sea peor que dentro de muestra (sobreajuste medible).

Implementación (fiel al paper):
- S = 16 particiones cronológicas de la serie de pnls por orden de cierre.
- C(16, 8) = 12,870 submuestras train/test balanceadas.
- sharpe por trade sin rf (media/desv), exactamente como el paper.

Salida: distribución del logit, PBO, y comparación con el DSR manual
(n_trials=16) que la corrida ya reportó — ¿qué tan honesto era?
"""
import datetime
import itertools
import os
import sys

import numpy as np
import pandas as pd

TRADES_PATH = os.path.join("data", "cache", "universe50_phaseA_20260810_165713_trades.parquet")
S_PARTITIONS = 16
COMB_SIZE = 8


def sharpe(x: np.ndarray) -> float:
    if len(x) < 2 or np.std(x) == 0:
        return 0.0
    return float(np.mean(x) / np.std(x))


def main():
    out_path = os.path.join("data", "cache", f"pbo_cscv_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    trades = pd.read_parquet(TRADES_PATH).sort_values("exit_date")
    pnls = trades["pnl"].values

    out("=" * 72)
    out("PLAN §11 Fase 3 — PBO/CSCV (Bailey & López de Prado 2015)")
    out(f"Trades: {os.path.basename(TRADES_PATH)} | n={len(pnls)}")
    out(f"Particiones: S={S_PARTITIONS}, combinaciones C({S_PARTITIONS},{COMB_SIZE})="
        f"{np.math.comb(S_PARTITIONS, COMB_SIZE)}")
    out("=" * 72)

    # Particiones cronológicas
    edges = np.linspace(0, len(pnls), S_PARTITIONS + 1, dtype=int)
    partitions = [pnls[edges[i]:edges[i + 1]] for i in range(S_PARTITIONS)]
    out(f"\nTrades por partición: {[len(p) for p in partitions]}")

    logits = []
    n_combos = np.math.comb(S_PARTITIONS, COMB_SIZE)
    for k, combo in enumerate(itertools.combinations(range(S_PARTITIONS), COMB_SIZE)):
        if k % 2000 == 0:
            print(f"  combo {k}/{n_combos}", flush=True)
        in_set = set(combo)
        train = np.concatenate([partitions[i] for i in range(S_PARTITIONS) if i in in_set])
        test = np.concatenate([partitions[i] for i in range(S_PARTITIONS) if i not in in_set])
        logits.append(sharpe(test) - sharpe(train))

    logits = np.array(logits)
    pbo = float(np.mean(logits < 0))

    out("\n--- DISTRIBUCIÓN DEL LOGIT (sharpe_test - sharpe_train) ---")
    out(f"  n combos: {len(logits)}")
    for q in [5, 25, 50, 75, 95]:
        out(f"  p{q}: {np.percentile(logits, q):+.4f}")
    out(f"  media: {np.mean(logits):+.4f} | desv: {np.std(logits):.4f}")

    out("\n--- PBO (P[logit < 0]) ---")
    out(f"  PBO = {pbo:.4f}")
    out("  ADVERTENCIA METODOLÓGICA: con UNA configuración y submuestras balanceadas,")
    out("  el logit es ANTISIMÉTRICO por construcción (cada combinación tiene su")
    out("  complementaria con signo invertido) -> PBO converge a 0.5 SIEMPRE.")
    out("  NO es '50% de sobreajuste': es el NULO de selección (no hay selección")
    out("  entre configuraciones que medir). La información real está en la")
    out("  DISPERSIÓN del logit: ¿cuánto varía el rendimiento IS vs OOS?")
    spread = float(np.std(logits))
    out(f"\n  Lectura correcta (dispersión del logit, desv={spread:.3f}):")
    if spread < 0.10:
        out("    Dispersión baja: rendimiento estable IS vs OOS; poco riesgo de degradación.")
    elif spread < 0.20:
        out("    Dispersión moderada: la incertidumbre IS-vs-OOS es del orden del propio")
        out("    rendimiento — W2 negativo confirma que no hay ventaja persistente global.")
    else:
        out("    Dispersión alta: el rendimiento varía mucho según la submuestra;")
        out("    los números IS son poco informativos para el futuro.")

    out("\n--- COMPARACIÓN CON DSR MANUAL (n_trials=16) ---")
    out("  La corrida reportó DSR W1=0.0435 W2=0.0021 W3=0.2337 (V1, N_TRIALS=16).")
    out("  CSCV mide la ESTABILIDAD IS vs OOS de la misma configuración; el DSR")
    out("  mide la probabilidad de que el Sharpe bruto sea casualidad. Son dos")
    out("  lecturas complementarias de la misma pregunta.")

    out("\n--- POR VENTANA OOS (estabilidad local) ---")
    for label, s, e in [("W1 2020-2021", "2020-01-01", "2021-12-31"),
                        ("W2 2022-2023", "2022-01-01", "2023-12-31"),
                        ("W3 2024-2026", "2024-01-01", "2026-08-04")]:
        w = trades[(trades["exit_date"] >= s) & (trades["exit_date"] <= e)]
        out(f"  {label}: n={len(w)} sharpe_trade={sharpe(w['pnl'].values):+.4f}")

    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
