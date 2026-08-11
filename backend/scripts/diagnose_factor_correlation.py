"""
PLAN §11 Fase 1a — Correlación entre factores sobrevivientes.

Pregunta: ¿momentum, RSI, macro compuesto (y sentimiento, informativo) están
poco correlacionados? Si |rho| < 0.5 -> la combinación multivariada tiene
sentido (principio Renaissance: ventajas chicas descorrelacionadas). Si
|rho| > 0.7 -> combinar no agrega y el proyecto se archiva con evidencia.

Medida: Pearson + Spearman sobre el panel (solo días eligible, la población
donde el score se usa para operar), pooled y por régimen.

Nota metodológica: macro_composite y sentiment_v1 son series de MERCADO
(mismo valor para todos los símbolos del día) — su n efectivo es de días,
no de filas. Se reportan ambas lecturas.
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd

FACTORS = ["momentum_score", "rsi_score", "macro_composite", "sentiment_v1"]


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet — corre primero build_factor_panel.py")
    return files[-1]


def corr_table(df: pd.DataFrame, subset: pd.DataFrame, label: str, out):
    out(f"\n--- {label} ---")
    out(f"  n filas: {len(subset)} | días únicos: {subset['date'].nunique()}")
    for method in ["pearson", "spearman"]:
        out(f"\n  [{method}]")
        m = subset[FACTORS].corr(method=method)
        for i, a in enumerate(FACTORS):
            for b in FACTORS[i + 1:]:
                v = m.loc[a, b]
                flag = "OK (<0.5)" if abs(v) < 0.5 else ("OJO (0.5-0.7)" if abs(v) < 0.7 else "ARCHIVAR (>0.7)")
                out(f"    {a:16s} x {b:16s} = {v:+.4f}   {flag}")


def main():
    path = latest_panel()
    out_path = os.path.join("data", "cache", f"factor_corr_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    panel = pd.read_parquet(path)
    eligible = panel[panel["eligible"]].copy()

    out("=" * 72)
    out("PLAN §11 Fase 1a — Correlación entre factores sobrevivientes")
    out(f"Panel: {os.path.basename(path)}")
    out("=" * 72)

    # Correlación por DÍA (serie de mercado): macro/sentimiento no varían por símbolo
    daily = panel.groupby("date")[["macro_composite", "sentiment_v1"]].first()
    out("\n--- Correlación macro x sentimiento (n efectivo = días) ---")
    for method in ["pearson", "spearman"]:
        v = daily.corr(method=method).loc["macro_composite", "sentiment_v1"]
        out(f"  [{method}] macro x sentiment = {v:+.4f}  (n días = {len(daily)})")

    # Correlación por régimen (pooled por fila)
    for reg in sorted(eligible["regime"].unique()):
        corr_table(eligible, eligible[eligible["regime"] == reg], f"Régimen {reg} (pooled por fila)", out)

    corr_table(eligible, eligible, "TODOS los regímenes (pooled por fila)", out)

    # Veredicto resumido (pooled, criterio §11)
    m = eligible[FACTORS].corr(method="spearman")
    verdicts = []
    for i, a in enumerate(FACTORS):
        for b in FACTORS[i + 1:]:
            rho = abs(m.loc[a, b])
            verdicts.append(rho)
            status = "archivar" if rho > 0.7 else ("cautela" if rho > 0.5 else "ok")
            if rho > 0.5:
                out(f"\n  [VEREDICTO] {a} x {b}: |rho|={rho:.3f} -> {status}")
    out(f"\n  Máx |rho| entre pares: {max(verdicts):.3f} "
        f"-> {'ARCHIVAR combinación' if max(verdicts) > 0.7 else 'la combinación tiene sentido (1b)'}")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
