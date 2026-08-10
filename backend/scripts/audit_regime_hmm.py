"""
FASE 0a — AUDITORÍA DEL RÉGIMEN HMM 2025-2026.

Pregunta pre-registrada (PLAN_MEJORA):
¿El IC negativo del baseline G1 en OOS (2025-2026) se explica por un régimen
de mercado anómalo respecto del período IS, o el deterioro es transversal?

Diseño (sin lookahead):
- Fit del GlobalRegimeClassifier SOLO con datos <= 2024-12-31.
- Etiquetado walk-forward: para cada fecha t, decodificación Viterbi sobre la
  ventana [2015, t] con el modelo fiteado; estado de t = último estado.
  (Evita el lookahead suave del Viterbi global que usaría fechas futuras.)
- Estados remapeados por _align_states con métricas del período <= 2024
  (semántica tal como se la conocía antes del OOS).
- Registros de señal: misma construcción que diagnose_sentiment_oos.py
  (mismas constantes y pesos), evaluados en IS 2019-2024 y OOS 2025-2026.
- IC de G1 (baseline) y de V1 (aaii) condicional por régimen, con n_eff
  Newey-West, por horizonte.

Veredicto (criterio pre-registrado):
- CONCENTRADO: IC negativo OOS solo en el/los régimen/es dominantes OOS que
  eran raros en IS -> el deterioro es de régimen, no de la señal.
- TRANSVERSAL: IC negativo en varios regímenes, incluidos comunes al IS ->
  la señal perdió poder fuera de muestra de forma estructural.
- MIXTO: reportar la tabla completa sin sobre-interpretar.
"""
import os
import datetime

import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.market_sentiment import build_sentiment_frame
from app.core.probabilistic_engine import SignalQualityMetrics
from scripts.diagnose_sentiment_oos import (
    build_full_indicators,
    rolling_rank01,
    newey_west_neff,
    SYMBOLS,
    HORIZONS,
    STRIDE_DAYS,
    WARMUP_DAYS,
    RANK_WINDOW,
    V1_DOMINANCE,
)

MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
FIT_END = "2024-12-31"
IS_START = "2019-01-01"
OOS_START = "2025-01-01"
DATA_START = "2015-01-01"
DATA_END = "2026-08-09"

ENGINE_W = {"momentum_12_1": 0.35, "rsi14": 0.10, "walcl_growth_w": 0.05, "cot_retail_net_pct": 0.10}


def collect_records(price_data: dict, sentiment: pd.DataFrame, start: str, warmup_from: str) -> pd.DataFrame:
    """Registros de señal por símbolo, igual que el OOS pero parametrizable
    en inicio de evaluación (IS u OOS). Warmup desde warmup_from."""
    records = []
    for symbol in SYMBOLS:
        df = price_data.get(symbol)
        if df is None:
            continue
        n = len(df)
        if n < WARMUP_DAYS + max(HORIZONS):
            continue
        sent = sentiment.reindex(df.index)
        warm_i = int((df.index < pd.Timestamp(warmup_from)).sum())
        for i in range(warm_i, n - max(HORIZONS), STRIDE_DAYS):
            date = df.index[i]
            if date < pd.Timestamp(start):
                continue
            if date not in sentiment.index:
                continue
            row = {"symbol": symbol, "date": date}
            row["rsi14"] = df["rsi14"].iloc[i]
            row["momentum_12_1"] = df["momentum_12_1"].iloc[i] if "momentum_12_1" in df else np.nan
            row["er20"] = df["er20"].iloc[i]
            row["walcl_growth_w"] = sent.loc[date, "walcl_growth_w"]
            row["cot_retail_net_pct"] = sent.loc[date, "cot_retail_net_pct"]
            row["aaii_bullbear_spread"] = sent.loc[date, "aaii_bullbear_spread"]
            entry = df["close"].iloc[i]
            for h in HORIZONS + [1]:
                row[f"fwd_{h}"] = df["close"].iloc[i + h] / entry - 1
            records.append(row)
    return pd.DataFrame(records)


def label_regimes_walk_forward(clf: GlobalRegimeClassifier, price_data: dict) -> pd.Series:
    """Etiqueta cada fecha del panel con su régimen, decodificando Viterbi
    sobre la ventana [inicio, t] (sin usar fechas futuras)."""
    feats = clf._extract_features(price_data)
    dates = feats.index
    states = np.full(len(feats), -1, dtype=int)
    scaled_all = clf.scaler.transform(feats.values)
    for i in range(len(feats)):
        if i < 60:
            continue
        chunk = scaled_all[: i + 1]
        try:
            raw = clf.model.predict(chunk)
        except Exception:
            continue
        aligned = clf._align_states(raw, feats.iloc[: i + 1])
        states[i] = int(aligned[-1])
    return pd.Series(states, index=dates)


def main():
    out_path = os.path.join("data", "cache", f"regime_audit_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("FASE 0a — AUDITORÍA RÉGIMEN HMM (walk-forward, fit <= 2024-12-31)")
    log("=" * 72)

    # --- 1. Datos y fit del HMM sin lookahead ---
    macro = load_universe(MACRO_TICKERS, DATA_START, DATA_END)
    fit_data = {t: df[df.index <= pd.Timestamp(FIT_END)] for t, df in macro.items()}
    clf = GlobalRegimeClassifier(n_states=4)
    clf.fit(fit_data)
    log(f"HMM fiteado con {sum(len(d) for d in fit_data.values()) // len(fit_data)} días <= {FIT_END}")

    log("\n--- 1. Distribución de regímenes (días de trading) ---")
    reg_series = label_regimes_walk_forward(clf, macro)
    valid = reg_series[reg_series >= 0]
    is_mask = valid.index < pd.Timestamp(OOS_START)
    oos_mask = valid.index >= pd.Timestamp(OOS_START)
    log(f"    {'régimen':12s} {'IS 2019-2024':>12s} {'OOS 2025-2026':>12s} {'share IS':>9s} {'share OOS':>9s}")
    for r in range(4):
        name = clf.state_labels[r]
        n_is = int(is_mask.sum())
        n_oos = int(oos_mask.sum())
        n_is_r = int((is_mask & (valid == r)).sum())
        n_oos_r = int((oos_mask & (valid == r)).sum())
        log(f"    {name:12s} {n_is_r:>12d} {n_oos_r:>12d} {n_is_r / max(n_is, 1):>9.3f} {n_oos_r / max(n_oos, 1):>9.3f}")

    # --- 2. Registros de señal IS y OOS ---
    price_data = load_universe(SYMBOLS, "2018-01-01", DATA_END)
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}
    trading_dates = indicators_cache["SPY"].index
    sentiment = build_sentiment_frame(trading_dates)

    rec_is = collect_records(indicators_cache, sentiment, IS_START, warmup_from=IS_START)
    rec_oos = collect_records(indicators_cache, sentiment, OOS_START, warmup_from="2024-01-01")
    log(f"\nRegistros: IS={len(rec_is)}  OOS={len(rec_oos)}")

    def build_scores(rec: pd.DataFrame) -> pd.DataFrame:
        sub = rec.copy()
        s_mom = rolling_rank01(sub["momentum_12_1"])
        s_rsi = -rolling_rank01(sub["rsi14"])
        s_liq = rolling_rank01(sub["walcl_growth_w"])
        s_ret = rolling_rank01(sub["cot_retail_net_pct"])
        s_v1 = -rolling_rank01(sub["aaii_bullbear_spread"])
        tot = sum(ENGINE_W.values())
        w1 = {k: v / tot for k, v in ENGINE_W.items()}
        score1 = w1["momentum_12_1"] * s_mom + w1["rsi14"] * s_rsi + w1["walcl_growth_w"] * s_liq + w1["cot_retail_net_pct"] * s_ret
        sub["score1"] = score1
        sub["s_v1"] = s_v1
        return sub

    is_rec = build_scores(rec_is)
    oos_rec = build_scores(rec_oos)
    for rec in (is_rec, oos_rec):
        rec["regime"] = rec["date"].map(reg_series)

    # --- 3. IC condicional por régimen ---
    def ic_table(rec_a: pd.DataFrame, rec_b: pd.DataFrame, col: str, h: int, reg_series: pd.Series, clf: GlobalRegimeClassifier):
        fwd_col = f"fwd_{h}"
        rows = []
        for r in range(4):
            name = clf.state_labels[r]
            row = [name]
            for rec in (rec_a, rec_b):
                sub = rec[rec["regime"] == r].dropna(subset=[col, fwd_col])
                if len(sub) < 50:
                    row += [np.nan, np.nan, False, int(len(sub))]
                    continue
                ic = SignalQualityMetrics.compute_ic(sub[col], sub[fwd_col])
                n_eff = newey_west_neff(sub, col, h)
                sig = abs(ic) > 2.0 / np.sqrt(n_eff)
                row += [ic, n_eff, sig, int(len(sub))]
            rows.append(row)
        return rows

    def print_table(rows, col_label: str):
        log(f"    {'régimen':12s} {'IS ic':>8s} {'IS n_eff':>8s} {'IS sig':>7s} {'OOS ic':>8s} {'OOS n_eff':>8s} {'OOS sig':>7s} {'OOS n':>6s}")
        for row in rows:
            cells = [row[0].ljust(12)]
            for i in (1, 5):
                ic, n_eff, sig, n = row[i], row[i + 1], row[i + 2], row[i + 3]
                if pd.isna(ic):
                    cells.append(f"{'n<50':>8s} {'-':>8s} {'':>7s}")
                else:
                    cells.append(f"{ic:+8.4f} {n_eff:8.0f} {(' ***' if sig else ''):>7s}")
            log(f"    {' '.join(cells)}")

    log("\n--- 2. IC por régimen (G1 baseline) IS vs OOS ---")
    for h in HORIZONS + [1]:
        log(f"\n  horizonte {h}d — G1")
        print_table(ic_table(is_rec, oos_rec, "score1", h, reg_series, clf), "G1")

    log("\n--- 3. IC de V1 (aaii) por régimen IS vs OOS ---")
    for h in HORIZONS + [1]:
        log(f"\n  horizonte {h}d — V1")
        print_table(ic_table(is_rec, oos_rec, "s_v1", h, reg_series, clf), "V1")

    log("\n" + "=" * 72)
    log("Veredicto pendiente: revisar tablas (concentrado / transversal / mixto).")
    log(f"Out: {out_path}")


if __name__ == "__main__":
    main()
