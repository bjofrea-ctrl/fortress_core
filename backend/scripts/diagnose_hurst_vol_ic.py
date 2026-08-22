"""
T2.3 (PLAN_INTEGRACION_INDICAGENT.md) — Diagnóstico exploratorio de IC de las
features de régimen por símbolo: hurst_exponent y realized_vol_regime.

NO es un trial formal que consuma ledger: es diagnóstico exploratorio de
features nuevas (plan: "no agregarlas a signal_engine::_factor_scores hasta
que esto se mida"). La decisión de promover algo a señal/gate requeriría
pre-registro propio ANTES de correr.

Mediciones (misma disciplina que §36/trial_macd_bollinger.py):
  A) rank IC intra-día (Spearman por fecha sobre el corte transversal) de
     hurst_exponent vs fwd_return_20d — ¿el régimen de tendencia del símbolo
     predice retornos futuros? Sin prior direccional (hurst es régimen, no
     dirección): se reporta signo y significancia, sin afirmar edge.
  B) rank IC intra-día de realized_vol_regime vs fwd_return_20d — ¿la vol de
     corto/largo plazo predice retornos? Sin prior direccional.
  C) VALIDACIÓN del instrumento: rank IC de realized_vol_regime vs
     volatilidad realizada FUTURA a 20d (real_vol_20 = std de retornos de los
     próximos 20 días). Signo esperado +1 (clustering de volatilidad): valida
     que el proxy mide algo real, NO es edge de retorno.
  D) Ventanas W1 2020-2021, W2 2022-2023, W3 2024-2026-07-31 + total.
     SE Newey-West (L = min(12, n_dias//8)), t = mean_ic / se_nw.
  E) Referencia Bonferroni de la familia signal_diagnosis (n=19, dos colas):
     |t| > 3.008. Por ser exploratorio se reporta como referencia, no como
     gate de veredicto.

Output: data/cache/diagnose_hurst_vol_ic_<ts>.txt + RESUMEN_HURST_VOL_REGIME.md
"""
import datetime
import os
import sys

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from scipy import stats

START = "2018-01-01"
DATA_END = "2026-07-31"
MIN_SYMBOLS = 5
HORIZON = 20

# Umbral Bonferroni de la familia signal_diagnosis (n_trials=19, dos colas)
ALPHA_PER = 0.05 / (2 * 19)
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))  # 3.008

WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp(DATA_END)),
}


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusto Newey-West (pesos Bartlett) — copia fiel de §0.5a/§25/§36."""
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


def daily_ics(panel: pd.DataFrame, factor: str, target: str) -> np.ndarray:
    """Spearman por fecha (ranks sobre símbolos de ESA fecha) factor vs target."""
    ics = []
    for _date, day in panel.groupby("date"):
        d = day[[factor, target]].dropna()
        if len(d) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(d[factor], d[target])
        if np.isfinite(rho):
            ics.append(rho)
    return np.array(ics)


def rank_ic_stats(ics: np.ndarray, lags: int) -> dict:
    n = len(ics)
    if n == 0:
        return {"n_dias": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_dias": int(n), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def build_panel() -> pd.DataFrame:
    price_data = load_universe(SYMBOLS, START, DATA_END)
    frames = []
    for sym, df in price_data.items():
        ind = calculate_all_indicators(df)
        ind = ind.copy()
        ind["symbol"] = sym
        ret = ind["close"].pct_change()
        ind["real_vol_20"] = ret.rolling(HORIZON).std().shift(-HORIZON)
        ind["fwd_20"] = ind["close"].shift(-HORIZON) / ind["close"] - 1
        cols = ["date", "symbol", "hurst_exponent", "realized_vol_regime",
                "real_vol_20", "fwd_20"]
        ind.index.name = "date"
        frames.append(ind.reset_index()[cols])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values("date").reset_index(drop=True)


def main() -> int:
    out_path = os.path.join(
        "data", "cache",
        f"diagnose_hurst_vol_ic_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("T2.3 — Diagnóstico EXPLORATORIO de IC: hurst_exponent + realized_vol_regime")
    out(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {DATA_END} | horizonte fwd {HORIZON}d")
    out(f"Umbral referencia familia signal_diagnosis (n=19, dos colas): |t| > {THRESHOLD:.3f}")
    out(f"Ventanas: " + ", ".join(f"{k} {v[0].date()}->{v[1].date()}" for k, v in WINDOWS.items()))
    out("NOTA: exploratorio — NO consume ledger. Sin promoción a señal/gate.")
    out("=" * 78)

    panel = build_panel()
    out(f"\nPanel: {len(panel)} filas | {panel['date'].nunique()} fechas | "
        f"{panel['symbol'].nunique()} símbolos")
    out(f"Rango fechas: {panel['date'].min().date()} -> {panel['date'].max().date()}")

    def window_stats(sub, factor, target, lags_cap=12):
        ics = daily_ics(sub, factor, target)
        L = min(lags_cap, len(ics) // 8) if len(ics) else 0
        return rank_ic_stats(ics, L), L

    # A) Hurst vs fwd_20
    out("\n" + "=" * 78)
    out("A) rank IC intra-día: hurst_exponent vs fwd_return_20d (sin prior direccional)")
    out(f"{'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s}")
    for name, (start, end) in WINDOWS.items():
        w = panel[(panel["date"] >= start) & (panel["date"] <= end)]
        res, L = window_stats(w, "hurst_exponent", "fwd_20")
        sig = "SIG" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD) else ""
        out(f"{name:7s} {res['n_dias']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {L:3d} {sig}")
    res, L = window_stats(panel, "hurst_exponent", "fwd_20")
    out(f"TOTAL   {res['n_dias']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
        f"{res['t']:+7.2f} {L:3d}")

    # B) realized_vol_regime vs fwd_20
    out("\n" + "=" * 78)
    out("B) rank IC intra-día: realized_vol_regime vs fwd_return_20d (sin prior direccional)")
    out(f"{'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s}")
    for name, (start, end) in WINDOWS.items():
        w = panel[(panel["date"] >= start) & (panel["date"] <= end)]
        res, L = window_stats(w, "realized_vol_regime", "fwd_20")
        sig = "SIG" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD) else ""
        out(f"{name:7s} {res['n_dias']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {L:3d} {sig}")
    res, L = window_stats(panel, "realized_vol_regime", "fwd_20")
    out(f"TOTAL   {res['n_dias']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
        f"{res['t']:+7.2f} {L:3d}")

    # C) realized_vol_regime vs future realized vol (validación del instrumento)
    out("\n" + "=" * 78)
    out("C) VALIDACIÓN: rank IC intra-día: realized_vol_regime vs real_vol_20 futura "
        "(clustering, signo esperado +1)")
    out(f"{'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s}")
    for name, (start, end) in WINDOWS.items():
        w = panel[(panel["date"] >= start) & (panel["date"] <= end)]
        res, L = window_stats(w, "realized_vol_regime", "real_vol_20")
        sig = "SIG+" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and res["t"] > 0) else ""
        out(f"{name:7s} {res['n_dias']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {L:3d} {sig}")
    res, L = window_stats(panel, "realized_vol_regime", "real_vol_20")
    out(f"TOTAL   {res['n_dias']:6d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
        f"{res['t']:+7.2f} {L:3d}")

    out("\nInterpretación:")
    out("- A y B miden poder PREDICTIVO DIRECCIONAL de las features de régimen")
    out("  sobre retornos futuros (edge de retorno). Sin prior: signo y significancia")
    out("  se reportan sin afirmar edge.")
    out("- C valida que realized_vol_regime captura persistencia de vol real (no edge).")
    out("- Un hallazgo nulo en A/B NO refuta el valor de condicionamiento por régimen:")
    out("  indica que no hay edge direccional directo; el rol de régimen es condicionar")
    out("  (distinto de gate/filtro binario — ver PLAN T2.3).")
    out(f"\nOut: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())