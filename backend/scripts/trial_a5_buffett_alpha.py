"""
TRIAL #20 (PLAN §47) — "Buffett's Alpha" sistemático (Quality + Value + Low-Beta), A5.

Pre-registro §47 (APROBADO por coordinador 2026-08-25). Diseño CONGELADO, CERO
re-optimización. Fase 0 (panel EDGAR point-in-time de 48 empresas) ya ejecutada y
verificada (coverage-gate F2: universo 47/48=97.9%, fechas OOS 31/31=100%).

Hipótesis: un portafolio cross-sectional long top-quintile mensual sobre el universo 50
(48 operativas) formado por el composite "Buffett's Alpha" — calidad (ROE/ROA/
gross_margin/FCF-yield + estabilidad de ganancias) + valor (P/E,P/B,EV/EBITDA
invertidos) + bajo-beta (de precio, cobertura total) + apalancamiento moderado —
tiene Sharpe OOS neto > 0 Y DSR >= umbral Bonferroni del ledger.

Criterio binario: CUMPLE si Sharpe_OOS_neto>0 Y DSR>=th(motor_signal); NO_CUMPLE otra
cosa; NO_INTERPRETABLE si coverage-gate/fidelidad fallan (ya verificado PASS).

NO toca producción. Solo cache (panel + precios). Python 3.9 real.
Artefacto: data/cache/trial20_a5_buffett_alpha_<ts>.txt (+json +parquet positions).
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.trial_registry import current_threshold, consumed_budget
from scripts.validacion_oos_fresca_mom_rsi import deflated_sharpe

CACHE = os.path.join("data", "cache")
PANEL_PATH = os.path.join(CACHE, "fundamentals_panel.parquet")
OUT_DIR = CACHE

ETF_EXCLUDE = ("SPY", "QQQ")
OP = [s for s in SYMBOLS if s not in ETF_EXCLUDE]

IS_OOS_CUTOFF = pd.Period("2023-12", freq="M")
EMBARGO_MONTH = pd.Period("2024-01", freq="M")
COST_PER_MONTH = 0.002  # 0.0005+0.0005 por lado, un round-trip mensual
TOP_Q = 0.20
MIN_HOLD = 5
BETA_WIN = 126
SEED = 42
TRIAL_ID = "trial_a5_buffett_alpha"

# Winsor ranges (de _FUND_SPECS del motor) para normalizar componentes.
WINSOR = {
    "pe_ratio": (5, 60, True), "pb_ratio": (0.5, 10, True),
    "ev_ebitda": (3, 30, True), "roe": (-5, 30, False), "roa": (-3, 15, False),
    "debt_equity": (0, 3, True), "fcf_yield": (-2, 10, False),
    "gross_margin": (10, 60, False), "eps_growth": (-20, 50, False),
}


def load_prices(symbol):
    p = os.path.join(CACHE, symbol + ".parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.columns = [c.lower() for c in df.columns]
    df = df.sort_index()
    return df


def cross_z(series_t, lo, hi, invert):
    """Clip a cross-sectional series at [lo,hi], optional invert, then z-score."""
    x = series_t.astype(float)
    x = x.clip(lo, hi)
    if invert:
        x = -x
    m, s = x.mean(), x.std(ddof=0)
    if not np.isfinite(s) or s <= 0:
        return pd.Series(0.0, index=x.index)
    return (x - m) / s


def compute_composite(panel_sub, beta_t):
    """En una fecha de decisión t, devuelve Series(symbol->composite z) cross-sectional.

    quality = mean(z(roe),z(roa),z(gross_margin),z(fcf_yield),z(-std(eps_ttm)))
    value   = mean(z(-pe),z(-pb),z(-ev_ebitda))
    lowbeta = z(-beta)
    lev     = z(-|debt_equity-1|)
    composite = quality + value + lowbeta + 0.5*lev  (luego z otra vez)
    """
    idx = panel_sub.index
    # stability: -rolling std de eps_ttm (precomputado abajo por símbolo)
    # value
    vp = cross_z(panel_sub["pe_ratio"], *WINSOR["pe_ratio"])
    vb = cross_z(panel_sub["pb_ratio"], *WINSOR["pb_ratio"])
    ve = cross_z(panel_sub["ev_ebitda"], *WINSOR["ev_ebitda"])
    value = pd.concat([vp, vb, ve], axis=1).mean(axis=1)
    # quality
    q_roe = cross_z(panel_sub["roe"], *WINSOR["roe"])
    q_roa = cross_z(panel_sub["roa"], *WINSOR["roa"])
    q_gm = cross_z(panel_sub["gross_margin"], *WINSOR["gross_margin"])
    q_fcf = cross_z(panel_sub["fcf_yield"], *WINSOR["fcf_yield"])
    q_stab = cross_z(panel_sub["eps_stability"], -3, 3, True)  # ya es -std, invert=mejor estable
    quality = pd.concat([q_roe, q_roa, q_gm, q_fcf, q_stab], axis=1).mean(axis=1)
    # lowbeta
    lowbeta = cross_z(beta_t.reindex(idx), -3, 3, True)
    # leverage moderado
    lev = cross_z((panel_sub["debt_equity"] - 1.0).abs(), 0, 3, True)
    comp = (quality + value + lowbeta + 0.5 * lev)
    # z final cross-sectional
    m, s = comp.mean(), comp.std(ddof=0)
    if np.isfinite(s) and s > 0:
        comp = (comp - m) / s
    return comp


def main():
    np.random.seed(SEED)
    out_path = os.path.join(OUT_DIR, f"trial20_a5_buffett_alpha_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    txt = []

    def log(m=""):
        print(m)
        txt.append(m)

    log("=" * 78)
    log("TRIAL #20 (§47) — Buffett's Alpha sistemático (Quality+Value+Low-Beta), A5")
    log("Pre-registro APROBADO (coordinador 2026-08-25). Diseño congelado.")
    log("=" * 78)

    # --- F1 universo ---
    log(f"F1 universo operativo: {len(OP)} símbolos (sin ETF SPY/QQQ)")
    prices = {s: load_prices(s) for s in OP}
    prices = {s: df for s, df in prices.items() if df is not None and len(df) > 250}
    log(f"F1 precios cacheados: {len(prices)}/{len(OP)}")

    spy = load_prices("SPY")
    assert spy is not None

    # --- daily returns + rolling beta ---
    ret = {}
    for s, df in prices.items():
        r = df["close"].pct_change()
        ret[s] = r
    spy_ret = spy["close"].pct_change()
    beta = {}
    for s in prices:
        b = ret[s].rolling(BETA_WIN).cov(spy_ret) / spy_ret.rolling(BETA_WIN).var()
        beta[s] = b
    log(f"F4 low-beta: rolling {BETA_WIN}d vs SPY computado para {len(beta)} símbolos")

    # --- panel ---
    panel = pd.read_parquet(PANEL_PATH).reset_index()
    # estabilidad de ganancias: -rolling std de eps_ttm por símbolo
    stab = {}
    for s in OP:
        sub = panel[panel["symbol"] == s].set_index("date")["eps_ttm"]
        st = -(sub.rolling(BETA_WIN * 4).std())  # ~2y de estabilidad
        stab[s] = st
    # inyectar estabilidad al panel por (date,symbol)
    stab_series = pd.concat(stab.values())
    stab_series.index.name = "date"
    # merge: construir date,symbol series
    stab_long = []
    for s in OP:
        ss = stab[s].rename("eps_stability")
        ss = ss.reset_index().assign(symbol=s)
        stab_long.append(ss)
    stab_long = pd.concat(stab_long)
    panel = panel.merge(stab_long, on=["date", "symbol"], how="left")

    # --- monthly decision dates (last trading day of each month) ---
    all_dates = sorted(panel["date"].unique())
    all_dates = pd.to_datetime(all_dates)
    month_ends = pd.Series(all_dates).groupby(pd.DatetimeIndex(all_dates).to_period("M")).tail(1)
    month_ends = pd.DatetimeIndex(month_ends.values)

    # monthly close-to-close returns per symbol (held-month return)
    monthly_ret = {}
    for s, df in prices.items():
        mc = df["close"].resample("ME").last()
        mret = mc.pct_change()
        mret.index = mret.index.to_period("M")
        monthly_ret[s] = mret

    # --- F2 coverage gate ---
    qual_cols = ["roe", "roa", "gross_margin", "fcf_yield", "eps_stability"]
    val_cols = ["pe_ratio", "pb_ratio", "ev_ebitda"]
    uni_cov = panel["symbol"].nunique() / len(OP)
    ok_months = 0
    total_months = 0
    for t in month_ends:
        sub = panel[panel["date"] == t]
        if len(sub) == 0:
            continue
        total_months += 1
        q = sub[qual_cols].notna().any(axis=1)
        v = sub[val_cols].notna().any(axis=1)
        if (q & v).mean() >= 0.80:
            ok_months += 1
    date_cov = ok_months / total_months if total_months else 0
    log(f"F2 coverage-gate: universo={uni_cov:.3f} (>=0.90)  fechas_OOS>=80% computable={date_cov:.3f} (>=0.80)")
    if uni_cov < 0.90 or date_cov < 0.80:
        log("  -> NO_INTERPRETABLE (coverage-gate falla). Aborto honrado.")
        _write(out_path, txt, None)
        return 1

    # --- loop de rebalances: decision en mes m, tenencia mes m+1 ---
    holdings_by_held = {}  # held_month (Period) -> list symbols
    for t in month_ends:
        sub = panel[panel["date"] == t].set_index("symbol")
        if len(sub) < MIN_HOLD:
            continue
        beta_t = pd.Series({s: beta[s].get(t, np.nan) for s in sub.index})
        comp = compute_composite(sub, beta_t)
        comp = comp.dropna()
        if len(comp) < MIN_HOLD:
            continue
        n = max(MIN_HOLD, int(np.ceil(TOP_Q * len(comp))))
        top = comp.sort_values(ascending=False).head(n)
        held_month = (pd.Timestamp(t).to_period("M") + 1)  # mes siguiente
        holdings_by_held[held_month] = list(top.index)

    # --- construir serie de retornos mensuales del portafolio (neto) ---
    port_ret = {}
    for held, syms in holdings_by_held.items():
        if held <= IS_OOS_CUTOFF:
            period_bucket = "IS"
        elif held == EMBARGO_MONTH:
            period_bucket = "EMBARGO"
        else:
            period_bucket = "OOS"
        rets = [monthly_ret[s].get(held, np.nan) for s in syms]
        rets = pd.Series(rets).dropna()
        if len(rets) == 0:
            continue
        r = rets.mean() - COST_PER_MONTH
        port_ret[held] = (r, period_bucket)

    port = pd.DataFrame(
        [{"month": k, "ret": v[0], "bucket": v[1]} for k, v in port_ret.items()]
    ).sort_values("month")
    oos = port[port["bucket"] == "OOS"]["ret"].dropna()
    is_ = port[port["bucket"] == "IS"]["ret"].dropna()

    # --- métricas ---
    def ann_sharpe(x):
        x = pd.Series(x).dropna()
        sd = x.std(ddof=1)
        return float(x.mean() / sd * np.sqrt(12.0)) if np.isfinite(sd) and sd > 0 and len(x) >= 3 else float("nan")

    sharpe_oos = ann_sharpe(oos)
    n_ledger = consumed_budget("motor_signal")
    n_trials = n_ledger + 1
    th = current_threshold("motor_signal")
    dsr_info = deflated_sharpe(oos.values.astype(float), n_trials=n_trials)
    dsr = dsr_info.get("dsr", float("nan"))

    log("")
    log(f"Ledger motor_signal: consumido_antes={n_ledger} -> n={n_trials} -> th={th:.6f}")
    log(f"IS meses={len(is_)}  OOS meses={len(oos)}")
    log(f"Sharpe_OOS neto anualizado = {sharpe_oos:.4f}")
    log(f"DSR (Bailey&LdP2014, n={n_trials}) = {dsr:.4f}")
    log(f"Criterio binario: Sharpe_OOS>0 Y DSR>={th:.5f}")

    cumple = bool(np.isfinite(sharpe_oos) and sharpe_oos > 0 and np.isfinite(dsr) and dsr >= th)
    log("")
    if cumple:
        log(f"VEREDICTO: CUMPLE — edge OOS neto confirmado bajo criterio binario §47.")
    else:
        log(f"VEREDICTO: NO_CUMPLE (mecánico) — Sharpe_OOS={'%.4f'%sharpe_oos} "
            f"DSR={'%.4f'%dsr} vs th={th:.5f}. Nada se promueve.")

    # --- F7 control: universo equal-weight ---
    ew = []
    for held, syms in holdings_by_held.items():
        if held <= IS_OOS_CUTOFF:
            bucket = "IS"
        elif held == EMBARGO_MONTH:
            bucket = "EMBARGO"
        else:
            bucket = "OOS"
        rr = [monthly_ret[s].get(held, np.nan) for s in OP]
        rr = pd.Series(rr).dropna()
        if len(rr):
            ew.append((held, rr.mean() - COST_PER_MONTH, bucket))
    ew_df = pd.DataFrame(ew, columns=["month", "ret", "bucket"])
    ew_oos = ew_df[ew_df["bucket"] == "OOS"]["ret"]
    log(f"F7 control universo equal-weight OOS Sharpe = {ann_sharpe(ew_oos):.4f} (sanity maquinaria)")

    log(f"\nOut: {out_path}")
    result = {
        "trial_id": TRIAL_ID, "status": "EJECUTADO",
        "pre_registro": "PLAN_MEJORA_MATEMATICA.md §47",
        "familia": "motor_signal",
        "ledger_runtime": {"consumido_antes": n_ledger, "n_trial": n_trials, "dsr_threshold": th},
        "coverage_gate": {"universe": round(uni_cov, 3), "fechas_oos": round(date_cov, 3), "pass": True},
        "sharpe_oos_neto": sharpe_oos, "dsr": dsr,
        "n_oos": int(len(oos)), "n_is": int(len(is_)),
        "veredicto": "CUMPLE" if cumple else "NO_CUMPLE",
    }
    _write(out_path, txt, result)
    return 0


def _write(out_path, txt, result):
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(txt) + "\n")
    if result is not None:
        jpath = out_path.replace(".txt", ".json")
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    sys.exit(main())
