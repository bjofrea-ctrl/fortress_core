"""
PLAN §11 Fase 2 — IC condicional por régimen real (HMM, refit trimestral).

Pregunta: ¿el score del motor predice distinto según el régimen, y el
promedio pooled lo esconde? Mide IC por factor y por score compuesto
DENTRO de cada estado HMM 0-3, sobre la población eligible del panel.

Si el IC condicional difiere en signo/estabilidad por régimen -> los
factor_weights fijos (mismo prior en los 4 regímenes, refine online) están
mal calibrados -> candidato a trial de pesos por régimen (gate §11).
Si no -> el promedio agregado no esconde nada y esto se archiva.
"""
import datetime
import glob
import os
import sys

import pandas as pd

from app.core.probabilistic_engine import SignalQualityMetrics

# Score del motor = priors de factor_weights (sin BMA online, que requiere
# trades cerrados — el panel es pre-trade).
MOM_W, RSI_W = 0.6639, 0.3361


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet — corre build_factor_panel.py")
    return files[-1]


def main():
    path = latest_panel()
    out_path = os.path.join("data", "cache", f"ic_by_regime_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    panel = pd.read_parquet(path)
    df = panel[panel["eligible"] & panel["fwd_return_20d"].notna()].copy()
    df["motor_score"] = MOM_W * df["momentum_score"] + RSI_W * df["rsi_score"]

    out("=" * 72)
    out("PLAN §11 Fase 2 — IC condicional por régimen real")
    out(f"Panel: {os.path.basename(path)}")
    out("=" * 72)

    signals = {
        "momentum_score": "Momentum",
        "rsi_score": "RSI",
        "macro_composite": "Macro compuesto",
        "motor_score": "Score motor (priors)",
    }

    rows = []
    for reg in sorted(df["regime"].unique()):
        sub = df[df["regime"] == reg]
        out(f"\n--- Régimen {reg} (n={len(sub)}, días={sub['date'].nunique()}) ---")
        for col, label in signals.items():
            ic = SignalQualityMetrics.compute_ic(sub[col], sub["fwd_return_20d"])
            ric = SignalQualityMetrics.compute_rank_ic(sub[col], sub["fwd_return_20d"])
            rows.append({"regime": reg, "signal": label, "ic": ic, "rank_ic": ric, "n": len(sub)})
            out(f"  {label:16s} ic={ic:+.4f}  rank_ic={ric:+.4f}  n={len(sub)}")

    out("\n--- Resumen pooled (para comparación) ---")
    for col, label in signals.items():
        ic = SignalQualityMetrics.compute_ic(df[col], df["fwd_return_20d"])
        ric = SignalQualityMetrics.compute_rank_ic(df[col], df["fwd_return_20d"])
        out(f"  {label:16s} ic={ic:+.4f}  rank_ic={ric:+.4f}  n={len(df)}")

    # Veredicto: estabilidad del motor_score entre regímenes
    out("\n--- VEREDICTO §11 Fase 2 ---")
    motor_by_regime = {r["regime"]: r["ic"] for r in rows if r["signal"] == "Score motor (priors)"}
    signs = {r: "pos" if v > 0 else "neg" for r, v in motor_by_regime.items()}
    out(f"  IC del score motor por régimen: {motor_by_regime}")
    if len(set(signs.values())) == 1 and all(v > 0.01 for v in motor_by_regime.values()):
        out("  Estable y positivo en todos los regímenes -> el promedio no esconde nada; se archiva.")
    else:
        out("  DIFIERE por régimen -> candidato a trial de pesos por régimen (gate §11).")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
