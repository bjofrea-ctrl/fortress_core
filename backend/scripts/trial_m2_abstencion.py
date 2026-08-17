"""
TRIAL #16 (PLAN §24) — Abstención calibrada M2 contra el baseline real (2026-08-17).
PRE-REGISTRADO antes de correr (ver §24 en el plan).

Pregunta: si el motor real (baseline universo 50) hubiera aplicado la abstención
calibrada M2 (Split Conformal sobre win_prob), ¿el VPP de lo que SÍ opera supera
el VPP del baseline que opera todo?

Diseño (fijado en §24):
  - Datos: data/cache/baseline_clean_20260811_150643_trades.parquet (286 trades reales).
  - Score: win_prob (el score real que el motor usa para sizing).
  - Outcome: ret = pnl / (shares * entry_price) — retorno neto real por trade.
  - Walk-forward acumulado SIN lookahead: para cada ventana, M2 se calibra SOLO con
    trades con entry_date ANTERIOR al inicio de la ventana.
  - Ventanas evaluables: W2 2022-2023 (calibra con trades < 2022-01-01, n=118),
    W3 2024-2026-08-04 (calibra con trades < 2024-01-01, n=167).
    W1 NO EVALUABLE por diseño (solo 24 trades de 2019 < piso n>=30 de M2).
  - Criterio (Bonferroni-2 unilateral, p < 0.025 por ventana, TODAS las ventanas):
    VPP_M2 > VPP_baseline; n_operados >= 30; tasa_abstencion <= 0.80.
    Fidelidad: cobertura empirica de M2 en [0.80, 0.97] (nominal 0.90); fuera de
    rango -> ventana NO INTERPRETABLE (ni exito ni fracaso).
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.conformal import ConformalAbstentionEngine, vpp_bajo_abstencion  # noqa: E402

TRADES_PARQUET = "data/cache/baseline_clean_20260811_150643_trades.parquet"
END = "2026-08-04"
ALPHA = 0.10
P_UMBRAL = 0.025  # Bonferroni-2 unilateral (0.05/2)
PISO_OPERADOS = 30
MAX_ABSTENCION = 0.80
COBERTURA_RANGO = (0.80, 0.97)
WINDOWS = [
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]


def z_test_dos_proporciones(p1: float, n1: int, p2: float, n2: int) -> float:
    """z unilateral (p1 > p2) de dos proporciones con correccion de continuidad."""
    if n1 == 0 or n2 == 0:
        return float("nan")
    p_hat = (p1 * n1 + p2 * n2) / (n1 + n2)
    if p_hat in (0.0, 1.0):
        return float("nan")
    se = np.sqrt(p_hat * (1 - p_hat) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return float("nan")
    # correccion de continuidad: resta la mitad de la unidad minima de diferencia
    cc = 0.5 * (1.0 / n1 + 1.0 / n2) / se
    z = ((p1 - p2) / se) - cc
    return float(z)


def main() -> None:
    trades = pd.read_parquet(TRADES_PARQUET)
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["ret"] = trades["pnl"] / (trades["shares"] * trades["entry_price"])
    trades = trades.sort_values("entry_date").reset_index(drop=True)

    lines = [
        "=" * 72,
        "TRIAL #16 — abstención calibrada M2 contra el baseline real",
        f"Corrida {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"Parquet: {TRADES_PARQUET}",
        f"Trades totales: {len(trades)} ({trades['entry_date'].min().date()} → "
        f"{trades['entry_date'].max().date()})",
        f"VPP baseline global (operar todo): {(trades['ret'] > 0).mean():.4f}",
        f"alpha={ALPHA} | umbral p<{P_UMBRAL} (Bonferroni-2) | piso operados "
        f">={PISO_OPERADOS} | abstencion <= {MAX_ABSTENCION:.0%} | "
        f"cobertura [{COBERTURA_RANGO[0]}, {COBERTURA_RANGO[1]}]",
        "=" * 72,
    ]

    veredictos = []
    for nombre, inicio, fin in WINDOWS:
        m_inicio = pd.Timestamp(inicio)
        m_fin = pd.Timestamp(fin)
        calib = trades[trades["entry_date"] < m_inicio]
        ventana = trades[(trades["entry_date"] >= m_inicio) & (trades["entry_date"] <= m_fin)]
        lines.append(f"\n--- {nombre} [{inicio} → {fin}] ---")
        lines.append(f"Calibración: n={len(calib)} trades (entry < {inicio})")
        lines.append(f"Ventana: n={len(ventana)} trades")

        if len(calib) < 30:
            lines.append("NO EVALUABLE por diseño: calibración < piso 30 de M2.")
            continue

        engine = ConformalAbstentionEngine(alpha=ALPHA)
        engine.calibrate(calib["win_prob"].to_numpy(), calib["ret"].to_numpy())

        preds = [engine.predict(s) for s in ventana["win_prob"].to_numpy()]
        outcomes = ventana["ret"].to_numpy()

        cobertura = engine.empirical_coverage(ventana["win_prob"].to_numpy(), outcomes)
        vpp_base = float((outcomes > 0).mean())
        resumen = vpp_bajo_abstencion(preds, outcomes)
        vpp_m2 = resumen["vpp"]
        n_operados = resumen["n_operados"]
        tasa_abs = resumen["tasa_abstencion"]

        z = z_test_dos_proporciones(vpp_m2, n_operados, vpp_base, len(outcomes))
        p_val = 1.0 - norm.cdf(z) if np.isfinite(z) else float("nan")

        lines.append(
            f"VPP_baseline={vpp_base:.4f} | VPP_M2={vpp_m2:.4f} | n_operados="
            f"{n_operados} | tasa_abstencion={tasa_abs:.2%} | cobertura="
            f"{cobertura:.4f}"
        )
        lines.append(
            f"z={z:.3f} | p={p_val:.4f} (umbral {P_UMBRAL}) | "
            f"quantile={engine._calibration.quantile:.5f} | "
            f"resid_mediana={engine._calibration.residuals_median:.5f} | "
            f"max_interval_width={engine.max_interval_width:.5f}"
        )

        # Fidelidad primero: cobertura fuera de rango -> NO INTERPRETABLE
        if not (COBERTURA_RANGO[0] <= cobertura <= COBERTURA_RANGO[1]):
            lines.append(f"FIDELIDAD: cobertura {cobertura:.3f} fuera de "
                         f"{COBERTURA_RANGO} -> ventana NO INTERPRETABLE")
            veredictos.append("NO_INTERPRETABLE")
            continue

        condiciones = {
            "VPP_M2 > VPP_baseline con p<0.025": (p_val < P_UMBRAL) and (vpp_m2 > vpp_base),
            "n_operados >= 30": n_operados >= PISO_OPERADOS,
            "tasa_abstencion <= 0.80": tasa_abs <= MAX_ABSTENCION,
        }
        for k, v in condiciones.items():
            lines.append(f"  [{'OK' if v else 'FALLA'}] {k}")
        if all(condiciones.values()):
            lines.append("VENTANA CUMPLE")
            veredictos.append("CUMPLE")
        else:
            lines.append("VENTANA NO CUMPLE")
            veredictos.append("NO_CUMPLE")

    # Contexto secundario (nunca criterio): retorno medio de operados vs todos
    lines.append("\n--- Contexto (no criterio) ---")
    lines.append(f"Ret medio por trade (todos): {trades['ret'].mean():+.5f}")
    lines.append(f"Ret medio por trade (pnl>0): {trades.loc[trades['pnl'] > 0, 'ret'].mean():+.5f}")
    lines.append(f"Ret medio por trade (pnl<0): {trades.loc[trades['pnl'] < 0, 'ret'].mean():+.5f}")

    if not veredictos:
        verdicto_final = "NO_EVALUABLE"
    elif all(v == "CUMPLE" for v in veredictos):
        verdicto_final = "CUMPLE"
    elif any(v == "NO_CUMPLE" for v in veredictos):
        verdicto_final = "NO_CUMPLE"
    elif all(v == "NO_INTERPRETABLE" for v in veredictos):
        verdicto_final = "NO_INTERPRETABLE"
    else:
        verdicto_final = "NO_CUMPLE"  # mezcla: exige TODAS las ventanas

    lines.append("\n" + "=" * 72)
    lines.append(f"VEREDICTO FINAL (pre-registrado §24): {verdicto_final}")
    lines.append(f"Ventanas: {', '.join(veredictos)}")
    lines.append("=" * 72)

    report = "\n".join(lines)
    print(report, flush=True)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact = f"data/cache/trial16_m2_abstencion_{stamp}.txt"
    with open(artifact, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    print(f"\nResumen: {artifact}", flush=True)


if __name__ == "__main__":
    main()
