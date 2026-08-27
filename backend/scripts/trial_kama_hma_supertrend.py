"""
PLAN_MEJORA_MATEMATICA §44 (2026-08-23) — Tarea M: KAMA/HMA/Supertrend,
familia de tendencia adaptativa.

Test pre-registrado en §44, escrito ANTES de correr. UN trial coordinado con 3
sub-hipótesis direccionales (los 3 miden DIRECCIÓN — verificación de origen en
PLAN_LARGO_PLAZO.md Tarea M), familia signal_diagnosis, n_trials_consumidos=1.
Ledger en runtime al pre-registrar: consumed=25 -> este es n=26 ->
current_threshold()=0.9961538461538462 -> alpha_trial=0.00384615 repartida
Bonferroni sobre m=9 celdas (3 indicadores x 3 ventanas) ->
|t| > z(0.99978633) = 3.5226 bilateral. El umbral se RELEE del ledger en esta
corrida con la misma fórmula (patrón §42); el artefacto cita el efectivo.

Factores CONGELADOS (§44, normalizados por precio para comparabilidad
cross-sectional):
  kama_dist        = (close - KAMA)/close, KAMA(er=10, fast=2, slow=30),
                     ER reusado de predictive_indicators.compute_efficiency_ratio
  hma_dist         = (close - HMA)/close, HMA(16) = WMA(2*WMA(n/2)-WMA(n), sqrt(n))
  supertrend_side  = {+1,-1}, Supertrend(ATR period=10, mult=3.0), flip estándar

Protocolo (fidelidad §0.5a, copia §41/§42): fwd_20 = close.shift(-20)/close - 1;
IC diario = Spearman(factor, fwd_20) por fecha sobre >=5 símbolos; SE
Newey-West L=min(12,n//8). Ventanas canónicas W1 2020-2021, W2 2022-2023,
W3 2024->2026-07-06. START=2015-01-02, DATA_END=2026-08-21 (solo cache, sin
descargas).

CRITERIO por indicador (pre-registrado): IC>0 con t_NW>+ZC en >=2/3 ventanas
computables (>=30 días con IC) -> CUMPLE. GLOBAL: CUMPLE si >=1 CUMPLE (OR,
protegida por Bonferroni m=9). Desglose por régimen HMM GOLDILOCKS-lag
(regime_gate.py, segundo uso real) REPORTADO como EXPLORATORIO — ningún
veredicto sale de ahí. Ninguno integra motor sin trial aparte.

Reglas: Python 3.9 real (backend/.venv). Lee SOLO cache parquet (sin descargas:
START/DATA_END dentro del rango cache, diff <=7 días como §41/§42). No toca
signal_engine.py/regime_gate.py/trial_registry.py en runtime (registro manual
al cierre).
Uso (UNA sola corrida):
  cd backend && .venv/bin/python -m scripts.trial_kama_hma_supertrend
Salida:
  data/cache/trial_kama_hma_supertrend_<YYYYMMDD_HHMMSS>.txt + .json
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.regime_gate import WalkForwardRegimeGate
from app.core.trial_registry import consumed_budget, current_threshold
from scipy import stats

TRIAL_ID = "trial_kama_hma_supertrend"
START = "2015-01-02"
DATA_END = "2026-08-21"
WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}
FACTORS = ("kama_dist", "hma_dist", "supertrend_side")
MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]

MIN_SYMBOLS = 5           # símbolos mínimos por fecha para un IC diario
MIN_DAYS_CELL = 30        # días con IC mínimos para celda primaria computable
MIN_DAYS_BUCKET = 30      # ídem por bucket en el desglose por régimen
LAG_BDAYS = 21            # rezago del estado HMM (un mes hábil)
M_TESTS = 9               # 3 indicadores x 3 ventanas (Bonferroni intra-trial)

# Umbral leído DEL LEDGER en runtime (§44 lo fija antes de correr)
N_CONSUMED = consumed_budget("signal_diagnosis")
ALPHA_TRIAL = 1.0 - current_threshold("signal_diagnosis")
ZC = float(stats.norm.ppf(1.0 - ALPHA_TRIAL / M_TESTS / 2.0))


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusta Newey-West (pesos Bartlett) — copia fiel de §0.5a/§41/§42."""
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


def bucket_stats(vals: np.ndarray) -> dict:
    n = len(vals)
    L = min(12, n // 8) if n else 0
    if n == 0:
        return {"n_days": 0, "mean_ic": float("nan"), "se_nw": float("nan"),
                "t": float("nan"), "L": 0}
    mean_ic = float(np.mean(vals))
    se = newey_west_se(vals, L)
    t = mean_ic / se if se > 0 else 0.0
    return {"n_days": int(n), "mean_ic": mean_ic, "se_nw": se, "t": float(t), "L": L}


def daily_ics(panel_w: pd.DataFrame, col: str, mask_col=None, mask_val=None) -> dict:
    """ICs diarios Spearman(col, fwd_20); si se pasa máscara, solo esas filas."""
    ics = {}
    for _d, day in panel_w.groupby("date"):
        if mask_col is not None:
            day = day[day[mask_col] == mask_val]
        dd = day[[col, "fwd_20"]].dropna()
        if len(dd) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(dd[col], dd["fwd_20"])
        if np.isfinite(rho):
            ics[_d] = rho
    return ics


def two_sample_delta(sa: dict, sb: dict) -> dict:
    """ΔIC = mean(A) − mean(B); SE_diff = sqrt(SE_A²+SE_B²) (independencia declarada)."""
    ma, mb = sa["mean_ic"], sb["mean_ic"]
    sea, seb = sa["se_nw"], sb["se_nw"]
    delta = ma - mb
    se_diff = float(np.sqrt(sea ** 2 + seb ** 2)) if np.isfinite(sea) and np.isfinite(seb) \
        else float("nan")
    t = delta / se_diff if np.isfinite(se_diff) and se_diff > 0 else float("nan")
    computable = (sa["n_days"] >= MIN_DAYS_BUCKET and sb["n_days"] >= MIN_DAYS_BUCKET
                  and np.isfinite(t))
    return {"delta_ic": float(delta), "t": float(t), "se_diff": se_diff,
            "computable": bool(computable)}


def build_panel() -> tuple:
    price = load_universe(SYMBOLS, START, DATA_END)
    frames = []
    for sym, df in price.items():
        ind = calculate_all_indicators(df)
        if ind.empty:
            continue
        ind = ind.copy()
        ind["fwd_20"] = ind["close"].shift(-20) / ind["close"] - 1
        ind["symbol"] = sym
        cols = list(FACTORS) + ["fwd_20"]
        ind.index.name = "date"
        frames.append(ind.reset_index()[["date", "symbol"] + cols])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return price, panel.sort_values("date").reset_index(drop=True)


def goldilocks_lagged(dates_index: pd.DatetimeIndex) -> tuple:
    """Estado HMM walk-forward (favorable=GOLDILOCKS) REZAGADO LAG_BDAYS hábiles.
    Segundo uso real de regime_gate.py (M3) — idéntico a §42a."""
    macro = load_universe(MACRO_TICKERS, START, DATA_END)
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0}))
    labels, diag = gate.label_series(macro)
    lab_idx = labels.index
    targets = dates_index - pd.offsets.BDay(LAG_BDAYS)
    pos = lab_idx.searchsorted(targets, side="right") - 1
    out = pd.Series(np.nan, index=dates_index)
    valid = pos >= 0
    out.loc[valid] = labels.values[pos[valid]].astype(float)
    return out, diag


def main() -> int:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join("data", "cache", "%s_%s.txt" % (TRIAL_ID, ts))
    json_path = os.path.join("data", "cache", "%s_%s.json" % (TRIAL_ID, ts))

    def out(msg=""):
        print(msg)
        with open(txt_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §44 — Tarea M: KAMA/HMA/Supertrend (tendencia adaptativa)")
    out("UN trial coordinado, 3 indicadores x 3 ventanas = m=%d tests primarios" % M_TESTS)
    out("Ledger runtime: signal_diagnosis consumido=%d -> n=%d | "
        "current_threshold=%.16f" % (N_CONSUMED, N_CONSUMED + 1,
                                     1.0 - ALPHA_TRIAL))
    out("alpha_trial=%.8f / m=%d -> alpha_per_test=%.8f bilateral | "
        "|t| > z = %.4f" % (ALPHA_TRIAL, M_TESTS, ALPHA_TRIAL / M_TESTS, ZC))
    out("Ventanas: " + ", ".join("%s %s->%s" % (k, v[0].date(), v[1].date())
                                 for k, v in WINDOWS.items()))
    out("=" * 78)

    # ---------- Fidelidad ----------
    checks = {}
    price, panel = build_panel()
    checks["F1_universo50"] = {
        "simbolos_cargados": len(price),
        "esperado": len(SYMBOLS),
        "ok": len(price) == len(SYMBOLS),
    }
    clf_probe = GlobalRegimeClassifier(n_states=4)
    checks["F4_determinismo_seed42"] = {
        "hmm_random_state": int(clf_probe.model.random_state),
        "ok": int(clf_probe.model.random_state) == 42,
    }
    out("\nFidelidad F1 universo: %d/%d cargadas | F4 seed HMM: %s" % (
        len(price), len(SYMBOLS), checks["F4_determinismo_seed42"]["hmm_random_state"]))
    out("Panel: %d filas | %d fechas | %d símbolos | %s -> %s" % (
        len(panel), panel["date"].nunique(), panel["symbol"].nunique(),
        panel["date"].min().date(), panel["date"].max().date()))
    for f in FACTORS:
        frac_finite = float(panel[f].notna().mean())
        desc = panel[f].describe()
        out("Sanidad %s: cobertura=%.3f | media=%+.6f p50=%+.6f" % (
            f, frac_finite, desc["mean"], desc["50%"]))

    cov_meses = {}
    for wname, (w0, w1) in WINDOWS.items():
        wd = panel[(panel["date"] >= w0) & (panel["date"] <= w1)]["date"]
        cov_meses[wname] = int(wd.dt.to_period("M").nunique())
    checks["F2_cobertura_meses"] = {"meses_con_datos": cov_meses,
                                    "esperado_aprox": {"W1": 24, "W2": 24, "W3": 30}}
    out("\nF2 cobertura meses con datos: %s" % cov_meses)

    # ---------- Edge pooled TOTAL por factor (F3, informativo) ----------
    out("\n--- F3 edge pooled TOTAL (informativo, no gatea) ---")
    for f in FACTORS:
        tot = daily_ics(panel, f)
        st_tot = bucket_stats(np.array(list(tot.values())))
        checks.setdefault("F3_edge_total_pooled", {})[f] = {
            "mean_ic": st_tot["mean_ic"], "n_days": st_tot["n_days"],
            "positivo": bool(st_tot["mean_ic"] > 0)}
        out("  %-16s IC=%+.4f (t=%+.2f, n=%d días)" % (
            f, st_tot["mean_ic"], st_tot["t"], st_tot["n_days"]))

    # ---------- Celdas PRIMARIAS: 3 factores x 3 ventanas ----------
    results = {}
    out("\n" + "=" * 78)
    out("TESTS PRIMARIOS (gatean): rank IC intra-día vs fwd_20, criterio "
        "IC>0 y t_NW>+%.4f en >=2/3 ventanas" % ZC)
    header = ("%-16s %-4s %7s %10s %9s %8s %5s"
              % ("factor", "win", "n_días", "mean_IC", "SE_NW", "t", "L"))
    for f in FACTORS:
        results[f] = {}
        out("\n%s" % header)
        for wname, (w0, w1) in WINDOWS.items():
            w = panel[(panel["date"] >= w0) & (panel["date"] <= w1)]
            ic = daily_ics(w, f)
            cell = bucket_stats(np.array(list(ic.values())))
            computable = cell["n_days"] >= MIN_DAYS_CELL
            sig = bool(computable and cell["mean_ic"] > 0 and cell["t"] > ZC)
            cell.update({"computable": bool(computable), "sig_pos": sig})
            results[f][wname] = cell
            out("%-16s %-4s %7d %10s %9s %8s %5d -> computable=%s sig=%s"
                % (f, wname, cell["n_days"], "%+.4f" % cell["mean_ic"],
                   "%.4f" % cell["se_nw"], "%+.2f" % cell["t"], cell["L"],
                   computable, sig))

    # ---------- Veredictos mecánicos ----------
    out("\n" + "=" * 78)
    out("VEREDICTOS MECÁNICOS (criterio §44)")
    verdicts = {}
    for f in FACTORS:
        sig_wins = [wn for wn, c in results[f].items() if c["sig_pos"]]
        comp_wins = [wn for wn, c in results[f].items() if c["computable"]]
        cumple = len(sig_wins) >= 2
        verdicts[f] = {"ventanas_sig": sig_wins,
                       "ventanas_computables": comp_wins,
                       "veredicto": "CUMPLE" if cumple else "NO_CUMPLE"}
        out("  %-16s SIG %s de computables %s -> %s"
            % (f, sig_wins, comp_wins,
               "CUMPLE" if cumple else "NO_CUMPLE"))
    global_verdict = ("CUMPLE" if any(v["veredicto"] == "CUMPLE"
                                      for v in verdicts.values()) else "NO_CUMPLE")
    out("GLOBAL (OR declarada): %s" % global_verdict)

    # ---------- Desglose por régimen (SECUNDARIO, EXPLORATORIO — no gatea) ----------
    out("\n" + "=" * 78)
    out("DESGLOSE POR RÉGIMEN (EXPLORATORIO — requisito de reporte de la spec, "
        "NINGÚN veredicto sale de acá)")
    dates_idx = pd.DatetimeIndex(sorted(panel["date"].unique()))
    gold_lag, diag = goldilocks_lagged(dates_idx)
    checks["F5_gate_walkforward"] = {
        "n_recalibraciones": int(diag.n_recalibraciones),
        "asserts_antileakage_pasados": True,   # label_series lanza si fallan
        "distribucion_estados": {str(k): int(v)
                                 for k, v in sorted(diag.distribucion_regimenes.items())},
    }
    out("recalibraciones=%d | fechas etiquetadas=%d | distribución estados=%s"
        % (diag.n_recalibraciones, diag.n_fechas_etiquetadas,
           checks["F5_gate_walkforward"]["distribucion_estados"]))
    panel["gold_lag"] = panel["date"].map(gold_lag)
    regime = {}
    for f in FACTORS:
        regime[f] = {}
        for wname, (w0, w1) in WINDOWS.items():
            w = panel[(panel["date"] >= w0) & (panel["date"] <= w1)]
            ic_a = daily_ics(w, f, "gold_lag", 1.0)
            ic_b = daily_ics(w, f, "gold_lag", 0.0)
            sa = bucket_stats(np.array(list(ic_a.values())))
            sb = bucket_stats(np.array(list(ic_b.values())))
            cell = two_sample_delta(sa, sb)
            cell.update({"A_gold": sa, "B_resto": sb})
            regime[f][wname] = cell
            out("  %-16s %-4s ΔIC(gold−resto)=%+.4f t=%+.2f | n gold=%d resto=%d"
                " | EXPLORATORIO" % (
                    f, wname, cell["delta_ic"], cell["t"],
                    sa["n_days"], sb["n_days"]))
    pista = [(f, wn, c["t"]) for f in regime for wn, c in regime[f].items()
             if c["computable"] and abs(c["t"]) > ZC]
    if pista:
        out("PISTA exploratoria (|t|>%.2f, requiere trial propio, NO cambia veredicto): %s"
            % (ZC, pista))
    else:
        out("Sin pistas exploratorias sobre el umbral.")
    out("Artefacto: %s" % txt_path)

    payload = {
        "trial_id": TRIAL_ID,
        "status": "EJECUTADO",
        "pre_registro": "PLAN_MEJORA_MATEMATICA.md §44",
        "familia": "signal_diagnosis",
        "ledger_runtime": {"consumido_antes": N_CONSUMED,
                           "n_trial": N_CONSUMED + 1,
                           "current_threshold": 1.0 - ALPHA_TRIAL,
                           "alpha_trial": ALPHA_TRIAL, "m_tests": M_TESTS,
                           "alpha_per_test": ALPHA_TRIAL / M_TESTS, "z_critico": ZC},
        "ventanas": {k: [str(v[0].date()), str(v[1].date())]
                     for k, v in WINDOWS.items()},
        "congelado": {
            "kama_dist": "(close-KAMA(er10,f2,s30))/close, ER reusado de "
                         "predictive_indicators.compute_efficiency_ratio",
            "hma_dist": "(close-HMA(16))/close, HMA=WMA(2*WMA(n/2)-WMA(n),sqrt(n))",
            "supertrend_side": "{+1,-1} Supertrend(ATR10, mult 3.0), flip estándar",
            "target": "fwd_20=close.shift(-20)/close-1",
            "ic": "Spearman intra-día ≥5 símbolos",
            "nw": "L=min(12,n//8)"},
        "checks_fidelidad": checks,
        "resultados_primarios": results,
        "veredictos_por_indicador": verdicts,
        "veredicto_global": global_verdict,
        "regimen_exploratorio_no_gatea": regime,
        "timestamp": ts,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("\nARTIFACT:%s" % txt_path)
    print("ARTIFACT_JSON:%s" % json_path)
    print("VEREDICTO_GLOBAL:%s" % global_verdict)
    print("UMBRAL_ZC:%.4f" % ZC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
