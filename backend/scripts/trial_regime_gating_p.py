"""
PLAN_MEJORA_MATEMATICA §42 (2026-08-22) — Tarea P: regime gating de momentum_12_1.

Test pre-registrado en §42, escrito ANTES de correr. UN trial coordinado con 3
sub-hipótesis (opción documentada en el plan, líneas 789-792), familia
signal_diagnosis, n_trials_consumidos=1. Ledger en runtime al pre-registrar:
consumed=23 -> este es n=24 -> current_threshold()=0.9958333333333333 ->
alpha_trial=0.00416667 repartida Bonferroni sobre m=9 celdas
(3 condicionantes x 3 ventanas) -> |t| > z(0.99976852) = 3.5013 bilateral.

Condicionantes (todos ΔIC(favorable − desfavorable), signo esperado +1):
  (a) Estado HMM rezagado un mes via WalkForwardRegimeGate.label_series
      (favorable_states={0}=GOLDILOCKS, defaults recalib_every=63/min_history=756,
      macro SPY EFA QQQ GLD DBC TIP TLT AGG ^VIX): etiqueta de t−21 hábiles.
      Cooper-Gutierrez-Hameed 2004. PRIMER USO REAL de regime_gate.py (M3).
  (b) Vol realizada 63d de la cartera equal-weight momentum top-quintil mensual,
      tercil expanding estrictamente causal (burn-in 126).
      Barroso-Santa-Clara 2015.
  (c) Amihud agregada: media de |ret_1d|/(close*volume) del universo, rolling 21d,
      tercil expanding causal. Avramov-Cheng-Hameed 2016.

CRITERIO por condicionante: ΔIC>0 con t_NW>+ZC en ≥2/3 ventanas (celda computable
requiere ≥30 días/bucket). GLOBAL: CUMPLE si ≥1 condicionante CUMPLE (OR declarada).
Diagnóstico: nada integra motor sin trial aparte.

Reglas: Python 3.9 real (backend/.venv). Lee SOLO cache parquet (sin descargas:
START/DATA_END dentro del rango cache, diff <=7 dias como §41). No toca
indicators.py/signal_engine.py/regime_gate.py/trial_registry.py en runtime.
Uso (UNA sola corrida):
  cd backend && .venv/bin/python -m scripts.trial_regime_gating_p
Salida:
  data/cache/trial_regime_gating_p_<YYYYMMDD_HHMMSS>.txt + .json
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

TRIAL_ID = "regime_gating_p"
START = "2015-01-02"          # extendido solo para que min_history=756 cubra W1
DATA_END = "2026-08-21"       # cache termina 08-14/17: diff <=7d -> sin descargas
WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}
MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]

MIN_SYMBOLS = 5           # símbolos mínimos por fecha para un IC diario
MIN_DAYS_BUCKET = 30      # días con IC mínimos por bucket para celda computable
LAG_BDAYS = 21            # rezago del estado HMM (un mes hábil)
VOL_WINDOW = 63           # vol realizada de la cartera momentum (ruedas)
LIQ_WINDOW = 21           # rolling mensual de la Amihud agregada (ruedas)
BURN_IN = 126             # burn-in de los percentiles expanding (ruedas)
QUINTILE_N = 10           # top-quintil de 50
MIN_SYMS_MONTH_END = 40   # símbolos con momentum válido para decidir fin de mes
MIN_SYMS_AGG = 25         # símbolos válidos mínimos para el agregado Amihud diario
M_TESTS = 9               # 3 condicionantes x 3 ventanas (Bonferroni intra-trial)

# Umbral leído DEL LEDGER en runtime (§42 lo fija antes de correr)
N_CONSUMED = consumed_budget("signal_diagnosis")
ALPHA_TRIAL = 1.0 - current_threshold("signal_diagnosis")
ZC = float(stats.norm.ppf(1.0 - ALPHA_TRIAL / M_TESTS / 2.0))


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE robusta Newey-West (pesos Bartlett) — copia fiel de §0.5a/§41."""
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
    sig = bool(computable and delta > 0 and t > ZC)
    return {"delta_ic": float(delta), "t": float(t), "se_diff": se_diff,
            "computable": bool(computable), "sig_pos": sig}


def ics_by_bucket(panel_sub: pd.DataFrame, col: str, val_a, val_b) -> tuple:
    """ICs diarios Spearman(momentum_12_1, fwd_20) dentro de cada bucket por fecha."""
    ics_a, ics_b = {}, {}
    for _d, day in panel_sub.groupby("date"):
        for val, store in ((val_a, ics_a), (val_b, ics_b)):
            dd = day[day[col] == val][["momentum_12_1", "fwd_20"]].dropna()
            if len(dd) < MIN_SYMBOLS:
                continue
            rho, _ = stats.spearmanr(dd["momentum_12_1"], dd["fwd_20"])
            if np.isfinite(rho):
                store[_d] = rho
    return ics_a, ics_b


def expanding_tercile(series: pd.Series, burn_in: int = BURN_IN) -> pd.Series:
    """Tercil ESTRICTAMENTE causal: percentil de v_t contra valores < t (excluye hoy).
    floor(pct*3)+1 con pct en [0,1] -> buckets 1..3 deterministas."""
    vals = series.values.astype(float)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        v = vals[i]
        if not np.isfinite(v) or i < burn_in:
            continue
        hist = vals[:i]
        hist = hist[np.isfinite(hist)]
        if len(hist) == 0:
            continue
        pct = (float((hist < v).sum()) + 0.5 * float((hist == v).sum())) / len(hist)
        out[i] = float(np.floor(pct * 3.0)) + 1.0
    return pd.Series(out, index=series.index)


def build_panel() -> tuple:
    price = load_universe(SYMBOLS, START, DATA_END)
    frames = []
    for sym, df in price.items():
        ind = calculate_all_indicators(df)
        if ind.empty:
            continue
        ind = ind.copy()
        ind["ret_1d"] = ind["close"].pct_change()
        ind["dollar_vol"] = ind["close"] * ind["volume"]
        ind["fwd_20"] = ind["close"].shift(-20) / ind["close"] - 1
        ind["symbol"] = sym
        cols = ["momentum_12_1", "fwd_20", "ret_1d", "dollar_vol"]
        ind.index.name = "date"
        frames.append(ind.reset_index()[["date", "symbol"] + cols])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return price, panel.sort_values("date").reset_index(drop=True)


def vol_momentum_portfolio_series(panel: pd.DataFrame) -> pd.Series:
    """Retorno diario de la cartera equal-weight momentum top-quintil mensual.
    Decisión al cierre de cada mes (último hábil con >=MIN_SYMS_MONTH_END momentum
    válidos): top QUINTILE_N por momentum_12_1; durante el mes siguiente el retorno
    diario = media de los ret_1d de los miembros con datos ese día (>=MIN_SYMBOLS)."""
    p = panel.dropna(subset=["momentum_12_1"]).copy()
    p["ym"] = p["date"].dt.to_period("M")
    members_by_next = {}
    cnt = p.groupby(["ym", "date"])["symbol"].nunique().reset_index()
    for _ym, g in cnt.groupby("ym"):
        ok = g[g["symbol"] >= MIN_SYMS_MONTH_END]
        if ok.empty:
            continue
        dec_date = ok["date"].iloc[-1]
        day = p[p["date"] == dec_date]
        top = day.nlargest(QUINTILE_N, "momentum_12_1")["symbol"].tolist()
        members_by_next[_ym + 1] = top
    rets = {}
    panel_ym = panel["date"].dt.to_period("M")
    for nxt, top in members_by_next.items():
        sub = panel[(panel_ym == nxt) & (panel["symbol"].isin(top))]
        gmean = sub.groupby("date")["ret_1d"].agg(["mean", "count"])
        gmean = gmean[gmean["count"] >= MIN_SYMBOLS]
        for d, row in gmean.iterrows():
            rets[d] = row["mean"]
    return pd.Series(rets).sort_index()


def amihud_aggregate_series(panel: pd.DataFrame) -> pd.Series:
    """Amihud agregada: media diaria sobre el universo de |ret_1d|/(close*volume),
    luego media rolling LIQ_WINDOW ruedas. Días con <MIN_SYMS_AGG válidos -> NaN."""
    q = panel.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        q["illiq"] = np.abs(q["ret_1d"]) / q["dollar_vol"]
    q.loc[~np.isfinite(q["illiq"]), "illiq"] = np.nan
    agg = q.groupby("date")["illiq"].agg(["mean", "count"])
    agg = agg[agg["count"] >= MIN_SYMS_AGG]
    return agg["mean"].rolling(LIQ_WINDOW).mean()


def goldilocks_lagged(dates_index: pd.DatetimeIndex) -> tuple:
    """PRIMER USO REAL de regime_gate.py (M3): etiqueta walk-forward del HMM macro
    (favorable=GOLDILOCKS), REZAGADA LAG_BDAYS días hábiles. Devuelve Serie 1.0/0.0/NaN
    alineada a las fechas pedidas + diagnósticos del proceso walk-forward."""
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
    out("PLAN_MEJORA_MATEMATICA §42 — Tarea P: regime gating de momentum_12_1")
    out("UN trial coordinado, 3 sub-hipótesis x 3 ventanas = m=%d tests" % M_TESTS)
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

    # Edge pooled TOTAL (F3, informativo)
    tot = []
    for _d, day in panel.groupby("date"):
        dd = day[["momentum_12_1", "fwd_20"]].dropna()
        if len(dd) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(dd["momentum_12_1"], dd["fwd_20"])
        if np.isfinite(rho):
            tot.append(rho)
    st_tot = bucket_stats(np.array(tot))
    checks["F3_edge_total_pooled"] = {"mean_ic": st_tot["mean_ic"],
                                      "n_days": st_tot["n_days"],
                                      "positivo": bool(st_tot["mean_ic"] > 0)}
    out("F3 edge pooled TOTAL momentum_12_1 vs fwd_20: IC=%+.4f (t=%+.2f, n=%d) [%s]" % (
        st_tot["mean_ic"], st_tot["t"], st_tot["n_days"],
        "OK informativo" if st_tot["mean_ic"] > 0 else "ANOMALIA (reportar)"))

    # ---------- Condicionante (a): gate walk-forward rezagado ----------
    out("\n--- (a) Estado HMM rezagado %d hábiles vía regime_gate.py "
        "(WalkForwardRegimeGate, primer uso real) ---" % LAG_BDAYS)
    dates_idx = pd.DatetimeIndex(sorted(panel["date"].unique()))
    gold_lag, diag = goldilocks_lagged(dates_idx)
    checks["F5_gate_walkforward"] = {
        "n_recalibraciones": int(diag.n_recalibraciones),
        "asserts_antileakage_pasados": True,   # label_series lanza si fallan
        "distribucion_estados": {str(k): int(v)
                                 for k, v in sorted(diag.distribucion_regimenes.items())},
    }
    frac_gold = float(np.nanmean(gold_lag.values)) if gold_lag.notna().any() else float("nan")
    out("recalibraciones=%d | fechas etiquetadas=%d | distribución estados=%s"
        % (diag.n_recalibraciones, diag.n_fechas_etiquetadas,
           checks["F5_gate_walkforward"]["distribucion_estados"]))
    out("Fracción días GOLDILOCKS-rezagado (sobre etiquetados+lago): %.3f" % frac_gold)

    panel["gold_lag"] = panel["date"].map(gold_lag)

    # ---------- Condicionante (b): vol cartera momentum ----------
    out("\n--- (b) Vol realizada %dd de la cartera momentum top-quintil ---" % VOL_WINDOW)
    port_ret = vol_momentum_portfolio_series(panel)
    vol63 = port_ret.rolling(VOL_WINDOW).std(ddof=1)
    vol_ter = expanding_tercile(vol63)
    n_vol = int(vol_ter.notna().sum())
    dist_vol = vol_ter.value_counts().to_dict()
    out("Días con vol+tercil: %d | distribución terciles=%s" % (n_vol, dist_vol))
    panel["vol_tercil"] = panel["date"].map(vol_ter)

    # ---------- Condicionante (c): Amihud agregada ----------
    out("\n--- (c) Iliquidez Amihud agregada (rolling %dd) ---" % LIQ_WINDOW)
    amihud = amihud_aggregate_series(panel)
    liq_ter = expanding_tercile(amihud)
    out("Días con amihud+tercil: %d | distribución terciles=%s"
        % (int(liq_ter.notna().sum()), liq_ter.value_counts().to_dict()))
    panel["liq_tercil"] = panel["date"].map(liq_ter)

    # ---------- Fidelidad F2: cobertura de meses por ventana ----------
    cov_meses = {}
    for wname, (w0, w1) in WINDOWS.items():
        wd = panel[(panel["date"] >= w0) & (panel["date"] <= w1)]["date"]
        cov_meses[wname] = int(wd.dt.to_period("M").nunique())
    checks["F2_cobertura_meses"] = {"meses_con_datos": cov_meses,
                                    "esperado_aprox": {"W1": 24, "W2": 24, "W3": 30}}
    out("\nF2 cobertura meses con datos: %s" % cov_meses)

    # ---------- Celdas: 3 condicionantes x 3 ventanas ----------
    specs = [
        ("a_estado_hmm_rezagado", "gold_lag", 1.0, 0.0,
         "GOLDILOCKS-lag", "resto"),
        ("b_vol_cartera_momentum", "vol_tercil", 1.0, 3.0,
         "vol baja (t1)", "vol alta (t3)"),
        ("c_amihud_agregada", "liq_tercil", 1.0, 3.0,
         "iliquidez baja (t1)", "iliquidez alta (t3)"),
    ]
    results = {}   # results[cond][win] = cell dict
    for cond, col, va, vb, la, lb in specs:
        results[cond] = {}
        out("\n" + "=" * 78)
        out("CONDICIONANTE (%s): ΔIC = IC(%s) − IC(%s) | signo esperado +1"
            % (cond.split("_")[0], la, lb))
        header = ("%-7s %-18s %6s %9s %8s %7s %6s %-18s %6s %9s %8s %7s"
                  % ("ventana", "bucket", "n", "mean_IC", "SE_NW", "t", "L",
                     "", "n", "mean_IC", "SE_NW", "t"))
        out(header)
        for wname, (w0, w1) in WINDOWS.items():
            w = panel[(panel["date"] >= w0) & (panel["date"] <= w1)]
            ica, icb = ics_by_bucket(w, col, va, vb)
            sa = bucket_stats(np.array(list(ica.values())))
            sb = bucket_stats(np.array(list(icb.values())))
            cell = two_sample_delta(sa, sb)
            cell.update({"A": sa, "B": sb, "label_A": la, "label_B": lb})
            results[cond][wname] = cell
            out("%-7s %-18s %6d %9s %8s %7s %6d %-18s %6d %9s %8s %7s"
                % (wname, la, sa["n_days"], "%+.4f" % sa["mean_ic"],
                   "%.4f" % sa["se_nw"], "%+.2f" % sa["t"], sa["L"],
                   lb, sb["n_days"], "%+.4f" % sb["mean_ic"],
                   "%.4f" % sb["se_nw"], "%+.2f" % sb["t"]))
            out("        ΔIC=%+.4f t=%+.2f computable=%s sig(t>+%0.2f y Δ>0)=%s"
                % (cell["delta_ic"], cell["t"], cell["computable"], ZC,
                   cell["sig_pos"]))

    # ---------- Veredictos ----------
    out("\n" + "=" * 78)
    out("VEREDICTOS MECÁNICOS (criterio §42: ΔIC>0 con t_NW>+%.4f en ≥2/3 ventanas)"
        % ZC)
    verdicts = {}
    for cond in results:
        sig_wins = [w for w, cell in results[cond].items() if cell["sig_pos"]]
        comp_wins = [w for w, cell in results[cond].items() if cell["computable"]]
        cumple = len(sig_wins) >= 2
        verdicts[cond] = {"ventanas_sig": sig_wins, "ventanas_computables": comp_wins,
                          "veredicto": "CUMPLE" if cumple else "NO_CUMPLE"}
        out("  (%s): ventanas SIG %s de computables %s -> %s"
            % (cond.split("_")[0], sig_wins, comp_wins,
               "CUMPLE" if cumple else "NO_CUMPLE"))
    global_verdict = ("CUMPLE" if any(v["veredicto"] == "CUMPLE"
                                      for v in verdicts.values()) else "NO_CUMPLE")
    out("GLOBAL (OR declarada): %s" % global_verdict)
    out("=" * 78)
    out("Artefacto: %s" % txt_path)

    payload = {
        "trial_id": TRIAL_ID,
        "status": "EJECUTADO",
        "pre_registro": "PLAN_MEJORA_MATEMATICA.md §42",
        "familia": "signal_diagnosis",
        "ledger_runtime": {"consumido_antes": N_CONSUMED,
                           "n_trial": N_CONSUMED + 1,
                           "current_threshold": 1.0 - ALPHA_TRIAL,
                           "alpha_trial": ALPHA_TRIAL, "m_tests": M_TESTS,
                           "alpha_per_test": ALPHA_TRIAL / M_TESTS, "z_critico": ZC},
        "ventanas": {k: [str(v[0].date()), str(v[1].date())]
                     for k, v in WINDOWS.items()},
        "congelado": {"factor": "close.pct_change(252)*100 (indicators.py:277)",
                      "target": "fwd_20=close.shift(-20)/close-1",
                      "ic": "Spearman intra-día ≥5 símbolos",
                      "nw": "L=min(12,n//8)"},
        "checks_fidelidad": checks,
        "frac_goldilocks_lag": frac_gold,
        "resultados": results,
        "veredictos_por_condicionante": verdicts,
        "veredicto_global": global_verdict,
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
