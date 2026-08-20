"""
PLAN_MEJORA_MATEMATICA §36 (2026-08-20) — Tarea N: MACD (dirección) y Bollinger (régimen).

Test pre-registrado en §36, escrito ANTES de correr. Familia signal_diagnosis,
n_trials=19 (18 consumidos + 1), umbral Bonferroni de la familia:
   |t| > z(1 - 0.05/38) = 3.008  (dos colas, n=19)

2A — MACD (DIRECCIÓN): rank IC intra-día de macd_hist vs fwd_return_20d,
     Spearman por fecha + SE Newey-West (L=min(12, n_dias//8)), ventanas W1/W2/W3.
     Criterio: |t| > 3.008 con signo +1 en >=2/3 ventanas.

2B — Bollinger (RÉGIMEN), DOS mediciones declaradas antes de correr:
  (i)  VALIDACIÓN: rank IC de band_width vs volatilidad realizada futura
       (std de retornos diarios futuros) a 10d y 20d. Signo +1 esperado.
       NO dispara CUMPLE (es validación del instrumento, no edge).
  (ii) INTERACCIÓN: rank IC del compuesto mom_rsi=rank(mom)+rank(rsi) split por
       terciles de band_width por fecha (tranquilo/media/expansión) a 20d Y a 5-10d,
       + split por régimen HMM (fit <=2024-12-31, decodificación causal).
       Criterio interacción: |ΔIC(expansión-tranquilo)| >= 0.05 a 20d O a 5-10d,
       Y el IC del tercil ganador significativo (|t|>3.008) en >=1 ventana/horizonte.

VEREDICTO COMBINADO (un slot): CUMPLE si MACD CUMPLE O Bollinger-(ii) CUMPLE.

Reglas: Python 3.9 real (backend/.venv). NO toca indicadores.py/signal_engine.py/
trial_registry.py/market.py/live.py/predict.py. Lee el cache, no descarga nada.
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

from app.api.routes.opportunities_universe import SYMBOLS
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.regime_classifier import GlobalRegimeClassifier

START = "2018-01-01"
DATA_END = "2026-08-14"
FIT_END = "2024-12-31"
MIN_SYMBOLS = 5

# Umbral Bonferroni de la familia signal_diagnosis (n_trials=19, dos colas)
ALPHA_PER = 0.05 / (2 * 19)
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))  # 3.008

WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}

MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusto Newey-West (pesos Bartlett) — copia fiel de la de §0.5a/§25."""
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


def daily_ics(panel: pd.DataFrame, factor: str, target: str, min_sym: int = MIN_SYMBOLS) -> np.ndarray:
    """Spearman por fecha (ranks sobre símbolos de ESA fecha) factor vs target."""
    ics = []
    for _date, day in panel.groupby("date"):
        d = day[[factor, target]].dropna()
        if len(d) < min_sym:
            continue
        rho, _ = stats.spearmanr(d[factor], d[target])
        if np.isfinite(rho):
            ics.append(rho)
    return np.array(ics)


def rank_ic_stats(ics: np.ndarray, lags: int) -> dict:
    n = len(ics)
    if n == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(n), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def build_panel() -> pd.DataFrame:
    price_data = load_universe(SYMBOLS, START, DATA_END)
    frames = []
    for sym, df in price_data.items():
        ind = calculate_all_indicators(df)
        ind = ind.copy()
        ind["symbol"] = sym
        ret = ind["close"].pct_change()
        ind["real_vol_10"] = ret.rolling(10).std().shift(-10)
        ind["real_vol_20"] = ret.rolling(20).std().shift(-20)
        ind["band_width"] = (ind["bb_upper"] - ind["bb_lower"]) / ind["bb_middle"]
        ind["fwd_5"] = ind["close"].shift(-5) / ind["close"] - 1
        ind["fwd_10"] = ind["close"].shift(-10) / ind["close"] - 1
        ind["fwd_20"] = ind["close"].shift(-20) / ind["close"] - 1
        cols = ["date", "symbol", "macd_hist", "rsi14", "momentum_12_1", "band_width",
                "real_vol_10", "real_vol_20", "fwd_5", "fwd_10", "fwd_20"]
        ind.index.name = "date"
        frames.append(ind.reset_index()[cols])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    # ranks cross-sectional por fecha (pct rank) para mom/rsi -> compuesto
    panel["r_mom"] = panel.groupby("date")["momentum_12_1"].rank(pct=True)
    panel["r_rsi"] = panel.groupby("date")["rsi14"].rank(pct=True)
    panel["mom_rsi"] = panel["r_mom"] + panel["r_rsi"]
    # tercil de ancho de banda por fecha
    panel["tercil_bw"] = panel.groupby("date")["band_width"].transform(
        lambda s: pd.qcut(s, 3, labels=[0, 1, 2], duplicates="drop"))
    return panel.sort_values("date").reset_index(drop=True)


def label_regimes(macro: dict) -> pd.Series:
    """Régimen HMM walk-forward: fit <= FIT_END, decodificación causal día a día.

    Mismo patrón eficiente que audit_regime_hmm.py: features y scaler se calculan
    UNA vez; cada fecha se decodifica Viterbi sobre el prefijo [inicio, t] (usa solo
    datos <= t -> sin lookahead), tomando la última etiqueta.
    """
    fit_data = {t: df[df.index <= pd.Timestamp(FIT_END)] for t, df in macro.items()}
    clf = GlobalRegimeClassifier(n_states=4)
    clf.fit(fit_data)
    feats = clf._extract_features(macro)
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


def main() -> int:
    out_path = os.path.join(
        "data", "cache",
        f"trial_macd_bollinger_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §36 — Tarea N: MACD (dirección) y Bollinger (régimen)")
    out(f"Umbral familia signal_diagnosis (n=19, dos colas): |t| > {THRESHOLD:.3f}")
    out(f"Ventanas: " + ", ".join(f"{k} {v[0].date()}->{v[1].date()}" for k, v in WINDOWS.items()))
    out("=" * 78)

    panel = build_panel()
    out(f"\nPanel: {len(panel)} filas | {panel['date'].nunique()} fechas | "
        f"{panel['symbol'].nunique()} símbolos")
    out(f"Rango fechas: {panel['date'].min().date()} -> {panel['date'].max().date()}")

    # --- Régimen HMM ---
    out("\n--- Etiquetado de régimen HMM (fit <= 2024-12-31, causal) ---")
    macro = load_universe(MACRO_TICKERS, START, DATA_END)
    reg_series = label_regimes(macro)
    panel["regime"] = panel["date"].map(reg_series).astype("Int64")
    dist = panel["regime"].value_counts(dropna=True)
    for r in range(4):
        name = GlobalRegimeClassifier(n_states=4).state_labels.get(r, str(r))
        out(f"  régimen {r} ({name}): {int(dist.get(r, 0))} filas panel")

    def window_stats(sub, factor, target, lags_cap=12):
        ics = daily_ics(sub, factor, target)
        L = min(lags_cap, len(ics) // 8) if len(ics) else 0
        return rank_ic_stats(ics, L), L

    # ============ 2A — MACD (DIRECCIÓN) ============
    out("\n" + "=" * 78)
    out("2A — MACD: rank IC intra-día de macd_hist vs fwd_return_20d (signo esperado +1)")
    out(f"{'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s} {'|t|>3.008':>10s}")
    macd_results = {}
    for name, (start, end) in WINDOWS.items():
        w = panel[(panel["date"] >= start) & (panel["date"] <= end)]
        res, L = window_stats(w, "macd_hist", "fwd_20")
        macd_results[name] = res
        sig = "SIG+" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and res["t"] > 0) else "no"
        out(f"{name:7s} {res['n_days']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {L:3d} {sig:>10s}")
    res_total, L_total = window_stats(panel, "macd_hist", "fwd_20")
    out(f"TOTAL   {res_total['n_days']:6d} {res_total['mean_ic']:+9.4f} {res_total['se_nw']:8.4f} "
        f"{res_total['t']:+7.2f} {L_total:3d}")
    n_sig_macd = sum(
        1 for r in macd_results.values()
        if np.isfinite(r["t"]) and abs(r["t"]) > THRESHOLD and r["t"] > 0)
    macd_cumple = n_sig_macd >= 2
    out(f"\nMACD: ventanas SIG+: {n_sig_macd}/3 | criterio >=2/3 con signo +1 y |t|>{THRESHOLD:.2f}")
    out(f"VEREDICTO MACD (2A): {'CUMPLE' if macd_cumple else 'NO_CUMPLE'}")

    # ============ 2B(i) — Bollinger VALIDACIÓN ============
    out("\n" + "=" * 78)
    out("2B(i) — Bollinger VALIDACIÓN: band_width vs volatilidad realizada futura (signo +1)")
    out(f"{'target':12s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'|t|>3.008':>10s}")
    vol_results = {}
    for target in ("real_vol_20", "real_vol_10"):
        res, L = window_stats(panel, "band_width", target)
        vol_results[target] = res
        sig = "SIG+" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and res["t"] > 0) else "no"
        out(f"{target:12s} {res['n_days']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {sig:>10s}")
    boll_i_cumple = any(
        np.isfinite(r["t"]) and abs(r["t"]) > THRESHOLD and r["t"] > 0
        for r in vol_results.values())
    out(f"\nBollinger (i) VALIDACIÓN: {'CUMPLE' if boll_i_cumple else 'NO_CUMPLE'} "
        f"(validez del instrumento — NO dispara el trial)")

    # ============ 2B(ii) — INTERACCIÓN por tercil de banda ============
    out("\n" + "=" * 78)
    out("2B(ii) — INTERACCIÓN: rank IC de mom_rsi split por tercil de band_width")
    out(f"{'horizonte':9s} {'tercil':11s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s}")
    tercil_names = {0: "tranquilo", 1: "media", 2: "expansión"}
    tercil_ics = {}
    for target, label in (("fwd_20", "20d"), ("fwd_10", "10d"), ("fwd_5", "5d")):
        for terc in (0, 1, 2):
            sub = panel[panel["tercil_bw"] == terc]
            res, L = window_stats(sub, "mom_rsi", target)
            tercil_ics[(label, terc)] = res
            out(f"{label:9s} {tercil_names[terc]:11s} {res['n_days']:6d} "
                f"{res['mean_ic']:+9.4f} {res['se_nw']:8.4f} {res['t']:+7.2f}")

    def interaccion(horizon_label, t20_key, t10_key, t5_key):
        # |ΔIC(expansión - tranquilo)| en el horizonte de interés
        pairs = []
        for hk in (t20_key, t10_key, t5_key):
            ic_e = tercil_ics[(hk, 2)]["mean_ic"]
            ic_c = tercil_ics[(hk, 0)]["mean_ic"]
            if np.isfinite(ic_e) and np.isfinite(ic_c):
                pairs.append((hk, abs(ic_e - ic_c)))
        return pairs

    pairs = interaccion("20d", "20d", "10d", "5d")
    max_pair = max(pairs, key=lambda x: x[1], default=("none", 0.0))
    out(f"\nMáx |ΔIC(expansión−tranquilo)|: {max_pair[0]} = {max_pair[1]:+.4f}")
    # significancia del tercil ganador (el de mayor |IC| absoluto) en el horizonte del máximo
    winner_terc = 2 if abs(tercil_ics[(max_pair[0], 2)]["mean_ic"]) >= abs(tercil_ics[(max_pair[0], 0)]["mean_ic"]) else 0
    winner = tercil_ics[(max_pair[0], winner_terc)]
    winner_sig = bool(np.isfinite(winner["t"]) and abs(winner["t"]) > THRESHOLD)
    boll_ii_cumple = max_pair[1] >= 0.05 and winner_sig
    out(f"ΔIC>=0.05: {max_pair[1] >= 0.05} | tercil ganador IC significativo (|t|>{THRESHOLD:.2f}): {winner_sig}")
    out(f"VEREDICTO Bollinger (ii) INTERACCIÓN: {'CUMPLE' if boll_ii_cumple else 'NO_CUMPLE'}")

    # ============ 2B(ii) — split por régimen HMM ============
    out("\n" + "=" * 78)
    out("2B(ii) — INTERACCIÓN: rank IC de mom_rsi split por régimen HMM (mom_rsi vs fwd_20d)")
    names = GlobalRegimeClassifier(n_states=4).state_labels
    out(f"{'régimen':12s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s}")
    hmm_ics = {}
    for r in range(4):
        sub = panel[panel["regime"] == r]
        res, L = window_stats(sub, "mom_rsi", "fwd_20")
        hmm_ics[r] = res
        out(f"{names[r]:12s} {res['n_days']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} {res['t']:+7.2f}")

    # ============ VEREDICTO COMBINADO ============
    out("\n" + "=" * 78)
    out("VEREDICTO COMBINADO (familia signal_diagnosis, n=1 slot)")
    out(f"  MACD (2A):           {'CUMPLE' if macd_cumple else 'NO_CUMPLE'}")
    out(f"  Bollinger (i) val:   {'CUMPLE' if boll_i_cumple else 'NO_CUMPLE'} (validación, no edge)")
    out(f"  Bollinger (ii) inter:{'CUMPLE' if boll_ii_cumple else 'NO_CUMPLE'}")
    trial_cumple = macd_cumple or boll_ii_cumple
    out(f"  TRIAL CUMPLE = (MACD CUMPLE) OR (Bollinger-ii CUMPLE) -> "
        f"{'CUMPLE' if trial_cumple else 'NO_CUMPLE'}")
    out(f"\nOut: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
