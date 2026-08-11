"""
PLAN §11 Fase 1b → PLAN_MEJORA_MATEMATICA.md §4.3 (2026-08-11).

Pregunta: ¿una combinación LINEAL regularizada de momentum + rsi + macro
(sentiment_v1 informativo) predice mejor que el blend actual por |IC|?

Método (todo lineal — caveat §11: nada no-lineal con esta muestra):
- Features estandarizadas (StandardScaler fit SOLO en train).
- RidgeCV (alpha por CV interna) sobre filas eligible (la población operable).
- Validación PURGADA + EMBARGO: k-fold por bloques temporales consecutivos;
  del train se eliminan filas cuya ventana forward (+20d) solape con el test
  (purga) y se deja un gap de embargo tras cada bloque de test.
- Métricas OOS por fold y agregadas: IC, rank IC, ICIR.
- Benchmark: el blend actual del motor (pesos proporcionales a |IC|:
  momentum 0.0637, rsi 0.0322, macro 0.13 -> normalizados) y cada factor solo.

Cambio §4.3 (auditoría #2): el ridge deja de usar macro_composite (re-ponderado
con pesos |IC| tuneados in-sample, §3.2) y recibe las 3 componentes macro
CRUDAS como features separadas (dxy_ret_20d, gold_ret_20d, spy_ret_50d,
oil_ret_20d — retornos sin umbrales internos de cada regla, §3.3). El ridge
aprende los pesos por datos. ridge_3f (composite) se mantiene solo como
referencia histórica de trial #13, NO como candidato a re-intentar (regla §6).

Criterio §11: IC_ridge > IC_blend_actual y ICIR estable (>= 0.0, mejor si
positivo). Veredicto final lo decide el gate de Fase 0.5 (W2 vs W3).
"""
import datetime
import glob
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from app.core.backtest_engine import CALIBRATION_HORIZON_DAYS
from app.core.probabilistic_engine import SignalQualityMetrics

FEATURES = ["momentum_score", "rsi_score", "macro_composite"]
FEATURES_PLUS_SENT = FEATURES + ["sentiment_v1"]
MACRO_RAW_FEATURES = ["dxy_ret_20d", "gold_ret_20d", "spy_ret_50d", "oil_ret_20d"]
TARGET = "fwd_return_20d"
N_FOLDS = 5
HORIZON = CALIBRATION_HORIZON_DAYS

# Blend actual del motor: pesos proporcionales a |IC| medido
BLEND_WEIGHTS = {"momentum_score": 0.0637, "rsi_score": 0.0322, "macro_composite": 0.13}


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet — corre build_factor_panel.py")
    return files[-1]


def purged_folds(dates: np.ndarray, n_folds: int, horizon: int):
    """Bloques temporales consecutivos; cada fold devuelve (train_idx, test_idx)
    con purga + embargo aplicados al train."""
    n = len(dates)
    edges = np.linspace(0, n, n_folds + 1, dtype=int)
    for k in range(n_folds):
        test_lo, test_hi = edges[k], edges[k + 1]
        test_start, test_end = dates[test_lo], dates[test_hi - 1]
        purge_lo = test_start - pd.Timedelta(days=horizon * 1.5)
        embargo_hi = test_end + pd.Timedelta(days=horizon * 1.5)
        test_idx = np.arange(test_lo, test_hi)
        train_idx = np.array([
            i for i in range(n)
            if i not in test_idx
            and not (purge_lo <= dates[i] <= embargo_hi)
        ])
        yield train_idx, test_idx


def evaluate(signal: pd.Series, target: pd.Series) -> dict:
    ic = SignalQualityMetrics.compute_ic(signal, target)
    rank_ic = SignalQualityMetrics.compute_rank_ic(signal, target)
    return {"ic": ic, "rank_ic": rank_ic, "n": len(signal)}


def main():
    path = latest_panel()
    out_path = os.path.join("data", "cache", f"ridge_comb_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    panel = pd.read_parquet(path)
    missing = [c for c in MACRO_RAW_FEATURES if c not in panel.columns]
    if missing:
        raise SystemExit(
            f"Panel sin columnas macro crudas §4.3: {missing} — "
            "re-corre build_factor_panel.py"
        )
    df = panel[panel["eligible"] & panel[TARGET].notna()].copy()
    df = df.sort_values("date").reset_index(drop=True)
    dates = df["date"].values

    out("=" * 72)
    out("PLAN_MEJORA_MATEMATICA §4.3 — Ridge con macro crudo (purgado + embargo)")
    out(f"Panel: {os.path.basename(path)} | filas eligible: {len(df)} | folds: {N_FOLDS}")
    out(f"Horizonte: {HORIZON}d | purga/embargo: ±{int(HORIZON * 1.5)}d")
    out("=" * 72)

    folds = list(purged_folds(dates, N_FOLDS, HORIZON))

    models = {
        "blend_actual": None,   # pesos |IC|, sin entrenar
        "ridge_3f": FEATURES,   # referencia histórica (composite, trial #13)
        "ridge_3f+sent": FEATURES_PLUS_SENT,
        "ridge_macro_crudo": ["momentum_score", "rsi_score"] + MACRO_RAW_FEATURES,
        "ridge_macro_crudo+sent": ["momentum_score", "rsi_score", "sentiment_v1"] + MACRO_RAW_FEATURES,
    }
    for name, feats in models.items():
        if name == "blend_actual":
            wsum = sum(BLEND_WEIGHTS.values())
            w = {k: v / wsum for k, v in BLEND_WEIGHTS.items()}
            signal = sum(df[k] * v for k, v in w.items())
            res = evaluate(signal, df[TARGET])
            out(f"\n--- {name} (sin entrenar) ---")
            out(f"  ic={res['ic']:+.4f}  rank_ic={res['rank_ic']:+.4f}  n={res['n']}")
            models[name] = res
            continue

        fold_ics, fold_rank_ics = [], []
        oos_signal = np.full(len(df), np.nan)
        for train_idx, test_idx in folds:
            X_tr = df.loc[train_idx, feats].values
            y_tr = df.loc[train_idx, TARGET].values
            X_te = df.loc[test_idx, feats].values

            scaler = StandardScaler().fit(X_tr)
            X_tr_s, X_te_s = scaler.transform(X_tr), scaler.transform(X_te)

            model = RidgeCV(alphas=np.logspace(-4, 2, 30)).fit(X_tr_s, y_tr)
            pred = model.predict(X_te_s)
            oos_signal[test_idx] = pred
            fold_ics.append(SignalQualityMetrics.compute_ic(
                pd.Series(pred), pd.Series(df.loc[test_idx, TARGET].values)))
            fold_rank_ics.append(SignalQualityMetrics.compute_rank_ic(
                pd.Series(pred), pd.Series(df.loc[test_idx, TARGET].values)))

        oos = evaluate(pd.Series(oos_signal), df[TARGET])
        out(f"\n--- {name} (ridge purgado, alpha óptimo por fold) ---")
        out(f"  ic OOS pooled={oos['ic']:+.4f}  rank_ic={oos['rank_ic']:+.4f}  n={oos['n']}")
        for k, (ic, ric) in enumerate(zip(fold_ics, fold_rank_ics)):
            out(f"    fold {k}: ic={ic:+.4f} rank_ic={ric:+.4f}")
        ic_arr = np.array(fold_ics)
        out(f"  ICIR (fold-level)={np.mean(ic_arr) / np.std(ic_arr):+.3f} | folds positivos: "
            f"{int(np.sum(ic_arr > 0))}/{N_FOLDS}")
        models[name] = oos

    out("\n--- VEREDICTO vs criterio (blend actual = benchmark) ---")
    b = models["blend_actual"]
    for name in ["ridge_3f", "ridge_3f+sent", "ridge_macro_crudo", "ridge_macro_crudo+sent"]:
        r = models[name]
        delta = r["ic"] - b["ic"]
        out(f"  {name}: ic={r['ic']:+.4f} vs blend={b['ic']:+.4f} -> delta={delta:+.4f}")
    out("  Nota: ridge_3f es REFERENCIA histórica (trial #13 refutado, regla §6:"
        "\n        no reintentar como score del motor hasta gate Fase 0.5).")
    out(f"\nOut: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
