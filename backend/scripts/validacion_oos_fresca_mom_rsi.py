"""
PRE-REGISTRO VALIDACION_OOS_FRESCA_MOM_RSI.md — validación OOS fresca del baseline
momentum+RSI con definición EXACTA congelada (CERO re-optimización).

Contexto (2026-08-22): PBO/CSCV N=21 = 0.4688 → NO_CUMPLE sustancial (overfitting de
proceso, PLAN_MEJORA_MATEMATICA.md §40). El baseline NO se revoca pero NO es promovible
sin validación sobre datos que el proceso selectivo nunca vio. Esta corrida ES esa
validación:

- Parámetros CONGELADOS leídos del código de producción (SignalEngine.factor_weights,
  umbrales literales de generate_signal) — prohibido ajustar pesos/bandas/umbrales.
- Ventana OOS fresca: decisiones >= 2024-01 (post-corte IS/OOS 2023-12-31). El retorno
  mensual de enero-2024 se DESCARTA como embargo de 20 ruedas (CALIBRATION_HORIZON_DAYS,
  backtest_engine.py:23) por solapar el corte; el último mes parcial del cache también
  se excluye (horizonte != mensual).
- Portafolio equal-weight mensual vectorizado: señal al cierre del último día hábil del
  mes m (solo datos <= fecha de decisión), entrada a OPEN del primer hábil de m+1
  (execution_lag_days=1 fiel), salida a CLOSE del último hábil de m+1; sin señales ->
  cash. Costos config.py: COST_PER_SIDE 0.0005 + slippage 0.0005 -> 0.002 ida-y-vuelta
  por mes con posiciones (convención conservadora §39/§40).
- Métrica primaria: Sharpe anualizado NETO (mensual ×√12) + Deflated Sharpe Ratio de
  Bailey & López de Prado (2014, JoPM) en frecuencia nativa, con
  N_eff = consumed_budget("signal_diagnosis") del ledger al correr (conservador).
  V[SR_n]: proxy conservador auditado del repo (Fase 0b, backtest_engine.calculate_metrics)
  = varianza del estimador denom²/(T−1); reduce la fórmula canónica EXACTAMENTE a la
  implementación en uso del repo (comparable con todos los W1/W2/W3 históricos).
- Criterio binario SIN zona gris (§5 pre-registro):
      CUMPLE           si Sharpe_OOS > 0 Y DSR >= 0.95 (y fidelidad OK)
      NO_CUMPLE        cualquier otra cosa (mecánico, sin reinterpretar)
      NO_INTERPRETABLE si los checks de fidelidad F1-F6 fallan
- Datos: SOLO cache parquet existente (sin descargas nuevas).

Uso (UNA sola corrida):
  cd backend && .venv/bin/python -m scripts.validacion_oos_fresca_mom_rsi
Salida:
  data/cache/validacion_oos_fresca_mom_rsi_<YYYYMMDD_HHMMSS>.txt + .json
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.indicators import calculate_all_indicators
from app.core.probabilistic_engine import circular_block_bootstrap_ci
from app.core.signal_engine import SignalEngine
from app.core.trial_registry import consumed_budget, register_trial
from scipy.stats import norm

CACHE_DIR = os.path.join("data", "cache")
OUT_DIR = os.path.join("data", "cache")

IS_OOS_CUTOFF = pd.Period("2023-12", freq="M")   # IS termina acá (baseline lockeado <= corte)
OOS_FIRST_MONTH = pd.Period("2024-01", freq="M")  # primer mes OOS nominal
EMBARGO_MONTHS = 1                                # ene-2024 completo: ~21 ruedas >= CALIBRATION_HORIZON_DAYS=20
ENTRY_THRESHOLD = 0.60                            # signal_engine.py:216
RSI_SCORE_BAND = (45, 70)                         # rsi_score=0.8 (estricto)
RSI_GATE = (40, 75)                               # gate duro (estricto)
ADX_MIN = 20                                      # gate duro >=
VR_MIN = 1.0                                      # volume_ratio >=
PARTIAL_MONTH_TOL_DAYS = 5                        # margen para declarar "mes incompleto"
MIN_T_MONTHS = 24                                 # F6: no correr con menos
MIN_COVERAGE = 0.30                               # F4
DSR_THRESHOLD = 0.95                              # criterio §5
BOOTSTRAP_BLOCK = 3                               # meses por bloque (CI secundario)
BOOTSTRAP_REPS = 1000
SEED = 42
TRIAL_ID = "validacion_oos_fresca_mom_rsi"
FIDELITY_SAMPLES = ["SPY", "AAPL", "NVDA"]


def load_symbol(symbol):
    """OHLC crudo (columnas minúsculas) + indicadores completos del motor."""
    path = os.path.join(CACHE_DIR, symbol + ".parquet")
    if not os.path.exists(path):
        return None, None
    df = pd.read_parquet(path)
    df.columns = [c.lower() for c in df.columns]
    missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
    if missing:
        raise RuntimeError(symbol + ": columnas faltantes " + str(missing))
    df = df.sort_index()
    ind = calculate_all_indicators(df.copy())
    if len(ind) == 0:
        return None, None
    return df, ind


def vectorized_score(ind, w_mom, w_rsi):
    """Score compuesto EXACTO de _factor_scores/compute_score_series (diario)."""
    mom = ind["momentum_12_1"]
    ms = ((mom + 50.0) / 150.0).clip(0.0, 1.0)
    ms = ms.where(mom.notna(), 0.5)
    rsi_v = ind["rsi14"]
    rs = pd.Series(
        np.where(rsi_v.between(RSI_SCORE_BAND[0], RSI_SCORE_BAND[1], inclusive="neither"), 0.8, 0.4),
        index=ind.index,
    )
    rs = rs.where(rsi_v.notna(), 0.5)
    return ms * w_mom + rs * w_rsi


def vectorized_eligible(ind):
    """Gates duros EXACTOS de generate_signal/compute_factor_frame (diario)."""
    trend_ok = (ind["close"] > ind["ema50"]) & (ind["ema50"] > ind["ema200"])
    adx_ok = ind["adx14"] >= ADX_MIN
    rsi_ok = (ind["rsi14"] > RSI_GATE[0]) & (ind["rsi14"] < RSI_GATE[1])
    vr_ok = ind["volume_ratio"] >= VR_MIN
    return (trend_ok & adx_ok & rsi_ok & vr_ok).fillna(False)


def fidelity_vs_engine(engine, samples):
    """F2/F3: score y máscara elegible del script == funciones reales del motor."""
    report = {}
    ok_all = True
    for sym, _, ind in samples:
        w0 = engine.factor_weights[0]
        mine = vectorized_score(ind, w0["momentum"], w0["rsi"])
        ref = engine.compute_score_series(ind, regime_state=0)
        d_score = float(np.nanmax(np.abs(mine - ref))) if len(mine) else float("nan")
        mine_e = vectorized_eligible(ind)
        ref_e = engine.compute_factor_frame(ind)["eligible"]
        mism = int((mine_e != ref_e.fillna(False)).sum())
        ok = bool(d_score < 1e-12 and mism == 0)
        ok_all = ok_all and ok
        report[sym] = {
            "max_abs_diff_score": d_score,
            "eligible_mismatches": mism,
            "rows": int(len(ind)),
            "ok": ok,
        }
    report["ok_global"] = ok_all
    return report


def deflated_sharpe(returns, n_trials, var_sr_trials=None):
    """Deflated Sharpe Ratio — Bailey & López de Prado (2014), JoPM 15(3).

    En frecuencia NATIVA de `returns` (mensual acá, NO anualizado):

        DSR = Phi( (SR_hat − SR0) · sqrt(T−1) / sqrt(1 − g3·SR_hat + ((g4−1)/4)·SR_hat²) )
        SR0 = sqrt(V[SR_n]) · E_max(N_eff)
        E_max(N) = (1−gamma_euler)·PhiInv(1−1/N) + gamma_euler·PhiInv(1−1/(N·e))

    V[SR_n] (varianza ENTRE trials): sin Sharpes OOS comparables reconstruibles sin
    violar el freeze, se usa el proxy conservador ya auditado del repo (Fase 0b,
    backtest_engine.calculate_metrics): V[SR_n] := denom²/(T−1). Con ese valor la
    fórmula canónica reduce EXACTAMENTE a Phi((SR − sr_std·E_max)/sr_std) del repo.
    """
    r = pd.Series(returns).dropna().astype(float)
    T = int(len(r))
    if T < 4 or n_trials < 1:
        return {"dsr": float("nan"), "T": T}
    sd = r.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0:
        return {"dsr": float("nan"), "T": T}
    sr = float(r.mean() / sd)
    skew = float(r.skew())
    kurt_pearson = float(r.kurtosis()) + 3.0  # pandas da exceso; Bailey usa Pearson (normal=3)
    var_num = max(1.0 - skew * sr + ((kurt_pearson - 1.0) / 4.0) * sr * sr, 1e-12)
    denom = float(np.sqrt(var_num))
    gamma_euler = 0.5772156649
    e_max = float(
        (1.0 - gamma_euler) * norm.ppf(1.0 - 1.0 / n_trials)
        + gamma_euler * norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    )
    v_sr = float(var_sr_trials) if var_sr_trials is not None else var_num / (T - 1)
    sr0 = float(np.sqrt(v_sr)) * e_max
    dsr = float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))
    return {
        "dsr": dsr,
        "T": T,
        "sr_monthly": sr,
        "skew": skew,
        "kurt_pearson": kurt_pearson,
        "denominator_var_num": var_num,
        "n_eff_used": int(n_trials),
        "e_max": e_max,
        "v_sr_trials_used": v_sr,
        "v_sr_source": "proxy estimador denom^2/(T-1) (repo Fase 0b, conservador)" if var_sr_trials is None else "externo",
        "sr0": sr0,
    }


def ann_sharpe_monthly(x):
    x = pd.Series(x).dropna().astype(float)
    sd = x.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0 or len(x) < 3:
        return float("nan")
    return float(x.mean() / sd * np.sqrt(12.0))


def build_monthly_panels():
    """Paneles mensuales: snapshot (último hábil del mes, indicadores del motor)
    y open del primer hábil del mes para ejecución con lag 1.

    Devuelve (panels dict de DataFrame ym×symbol, meta dict).
    """
    raw_frames, ind_frames, cache_ends = [], [], {}
    for sym in SYMBOLS:
        raw, ind = load_symbol(sym)
        if raw is None:
            raise RuntimeError("F1 FALLO: sin datos para " + sym + " (universo debe ser 50/50)")
        cache_ends[sym] = str(raw.index.max().date())
        r = raw.copy()
        r["symbol"] = sym
        r["ym"] = r.index.to_period("M")
        ind_frames.append(ind.assign(symbol=sym))
        raw_frames.append(r)

    all_ind = pd.concat(ind_frames)
    all_ind["ym"] = all_ind.index.to_period("M")
    snap = all_ind.groupby(["symbol", "ym"], sort=True).tail(1)

    panels = {}
    for col in ("close", "ema50", "ema200", "adx14", "rsi14",
                "volume_ratio", "momentum_12_1"):
        panels[col] = snap.pivot(index="ym", columns="symbol", values=col).sort_index()

    open_first = {}
    close_raw_last = {}
    for r in raw_frames:
        sym = r["symbol"].iloc[0]
        g = r.groupby("ym", sort=True)
        open_first[sym] = g.head(1).set_index("ym")["open"]
        close_raw_last[sym] = g.tail(1).set_index("ym")["close"]
    panels["open_first"] = pd.DataFrame(open_first).sort_index()
    panels["close_last_raw"] = pd.DataFrame(close_raw_last).sort_index()

    meta = {"cache_end_global": max(cache_ends.values()), "cache_ends": cache_ends}
    return panels, meta


def main():
    t0 = datetime.datetime.now()
    np.random.seed(SEED)

    n_ledger = consumed_budget("signal_diagnosis")
    if n_ledger < 21:
        print("[warn] ledger signal_diagnosis=" + str(n_ledger) + " < 21 esperado — se usa el real (conservador si mayor)", file=sys.stderr)
    w0_engine = SignalEngine(regime_classifier=None).factor_weights[0]
    w_mom, w_rsi = float(w0_engine["momentum"]), float(w0_engine["rsi"])

    print("=" * 78)
    print("VALIDACION OOS FRESCA momentum+RSI — definicion EXACTA congelada")
    print("Pre-registro: PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md (2026-08-22)")
    print("=" * 78)
    print("Universo: %d simbolos canonicos | pesos motor: w_mom=%.4f w_rsi=%.4f" % (len(SYMBOLS), w_mom, w_rsi))
    print("Costos: 0.0005/lado + 0.0005 slippage -> 0.002 ida-y-vuelta/mes | ejecucion lag 1 (open date+1)")
    print("Ledger signal_diagnosis consumed_budget=%d -> N_eff DSR" % n_ledger)

    samples = []
    for sym in FIDELITY_SAMPLES:
        _, ind = load_symbol(sym)
        if ind is None:
            raise RuntimeError("F2/F3 sin muestra: " + sym)
        samples.append((sym, None, ind))
    fid = fidelity_vs_engine(SignalEngine(regime_classifier=None), samples)
    for sym, rep in fid.items():
        if sym == "ok_global":
            continue
        print("  fidelidad %s: max|d_score|=%.3e mism_eligible=%d rows=%d -> %s"
              % (sym, rep["max_abs_diff_score"], rep["eligible_mismatches"], rep["rows"],
                 "OK" if rep["ok"] else "FALLO"))

    print("Cargando paneles mensuales desde cache (sin descargas)...", flush=True)
    panels, meta = build_monthly_panels()
    close, ema50, ema200 = panels["close"], panels["ema50"], panels["ema200"]
    adx, rsi_v, vr, mom = panels["adx14"], panels["rsi14"], panels["volume_ratio"], panels["momentum_12_1"]
    open_first, close_last_raw = panels["open_first"], panels["close_last_raw"]

    months_idx = close.index
    n_symbols_loaded = int(close.shape[1])
    print("  simbolos cargados: %d/%d | meses en panel: %d (%s -> %s)"
          % (n_symbols_loaded, len(SYMBOLS), len(months_idx), months_idx[0], months_idx[-1]))

    momentum_score = ((mom + 50.0) / 150.0).clip(0.0, 1.0)
    momentum_score = momentum_score.where(mom.notna(), 0.5)
    rsi_score = pd.DataFrame(
        np.where((rsi_v > RSI_SCORE_BAND[0]) & (rsi_v < RSI_SCORE_BAND[1]), 0.8, 0.4),
        index=rsi_v.index, columns=rsi_v.columns,
    )
    rsi_score = rsi_score.where(rsi_v.notna(), 0.5)
    overall = w_mom * momentum_score + w_rsi * rsi_score

    eligible = (
        (close > ema50) & (ema50 > ema200)
        & (adx >= ADX_MIN)
        & (rsi_v > RSI_GATE[0]) & (rsi_v < RSI_GATE[1])
        & (vr >= VR_MIN)
    ).fillna(False)
    signal = eligible & (overall >= ENTRY_THRESHOLD)

    month_ret = close_last_raw / open_first - 1.0  # open(primer habil m+... ) -> close(ultimo habil m): horizonte mensual lag-1
    cost_per_rebalance = 2.0 * (0.0005 + 0.0005)

    gross_rows, net_rows, n_pos_rows = [], [], []
    for i, m in enumerate(months_idx):
        if i == 0:
            sel = pd.Series(False, index=close.columns)
        else:
            sel = signal.loc[months_idx[i - 1]].fillna(False)  # decision al cierre del mes anterior
        rets = month_ret.loc[m][sel].dropna()
        n_pos = int(len(rets))
        gross = float(rets.mean()) if n_pos else 0.0
        net = gross - (cost_per_rebalance if n_pos else 0.0)
        gross_rows.append(gross)
        net_rows.append(net)
        n_pos_rows.append(n_pos)
    gross_m = pd.Series(gross_rows, index=months_idx)
    net_m = pd.Series(net_rows, index=months_idx)
    n_pos_m = pd.Series(n_pos_rows, index=months_idx)

    # Ventana OOS efectiva (§3 pre-registro):
    # (a) solo meses >= primer mes OOS nominal;
    # (b) embargo: descartar EMBARGO_MONTHS=1 primeros meses OOS (ene-2024 completo,
    #     ~21 ruedas >= CALIBRATION_HORIZON_DAYS=20 — decision 2023-12-29 solapa corte);
    # (c) excluir mes parcial final del cache (ago-2026 cortado a 2026-08-14).
    oos_mask = months_idx >= OOS_FIRST_MONTH
    oos_months = months_idx[oos_mask]
    embargoed = oos_months[:EMBARGO_MONTHS]
    eff_months = oos_months[EMBARGO_MONTHS:]
    # (c) mes parcial final del cache fuera (horizonte != mensual). Regla: si la
    # última fecha disponible del cache (referencia SPY) está a más de
    # PARTIAL_MONTH_TOL_DAYS del fin de calendario del mes, el mes es parcial.
    partial_dropped = []
    ref_sym = "SPY" if "SPY" in close_last_raw.columns else close_last_raw.columns[0]
    ce = pd.Timestamp(meta["cache_ends"].get(ref_sym))
    while len(eff_months):
        p = eff_months[-1]
        cal_end = p.end_time.normalize()
        if (cal_end - ce).days > PARTIAL_MONTH_TOL_DAYS:
            partial_dropped.append(str(p))
            eff_months = eff_months[:-1]
        else:
            break

    T_eff = len(eff_months)
    print("Ventana OOS: nominal %d meses desde %s | embargo descarta %s | parcial final descartado %s"
          % (int(oos_mask.sum()), OOS_FIRST_MONTH, [str(x) for x in embargoed], partial_dropped))
    print("Meses efectivos: T=%d (%s -> %s)" % (T_eff, eff_months[0] if T_eff else "-", eff_months[-1] if T_eff else "-"))

    checks = {
        "F1_universo": {"cargados": n_symbols_loaded, "esperados": len(SYMBOLS), "ok": bool(n_symbols_loaded == len(SYMBOLS))},
        "F2_F3_fidelidad_motor": fid,
        "F4_cobertura": {},
        "F5_edge_bruto": {},
        "F6_T_minimo": {"T_efectivos": int(T_eff), "minimo": MIN_T_MONTHS},
    }
    if T_eff < MIN_T_MONTHS:
        need = MIN_T_MONTHS - T_eff
        est = (datetime.date.today() + datetime.timedelta(days=int(round(need * 30.4)))).isoformat()
        msg = ("F6 FALLIDA: T=%d < %d meses efectivos — NO CORRER segun pre-registro §2/§7. "
               "Fecha estimada de disponibilidad: ~%s (falta ~%d meses de datos frescos)." % (T_eff, MIN_T_MONTHS, est, need))
        print("[abort] " + msg, file=sys.stderr)
        checks["F6_T_minimo"]["ok"] = False
        checks["abort_reason"] = msg
        ts = "%s" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(os.path.join(OUT_DIR, TRIAL_ID + "_ABORT_" + ts + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"status": "ABORT_F6", "checks": checks}, fh, ensure_ascii=False, indent=2)
        return 2
    checks["F6_T_minimo"]["ok"] = True

    net_oos = net_m.loc[eff_months]
    gross_oos = gross_m.loc[eff_months]
    pos_oos = n_pos_m.loc[eff_months]

    active = pos_oos > 0
    coverage_ratio = float(active.mean())
    gross_active_mean = float(gross_oos[active].mean()) if active.any() else 0.0
    checks["F4_cobertura"] = {
        "meses_con_senal": int(active.sum()), "T": T_eff,
        "ratio": round(coverage_ratio, 4), "min": MIN_COVERAGE,
        "ok": bool(coverage_ratio >= MIN_COVERAGE),
    }
    checks["F5_edge_bruto"] = {
        "mean_bruto_meses_con_senal": round(gross_active_mean, 6),
        "positivo": bool(gross_active_mean > 0), "ok": bool(gross_active_mean > 0),
    }
    fidelity_ok = bool(checks["F1_universo"]["ok"] and fid["ok_global"]
                       and checks["F4_cobertura"]["ok"] and checks["F5_edge_bruto"]["ok"])
    for k in ("F1_universo", "F4_cobertura", "F5_edge_bruto"):
        if not checks[k]["ok"]:
            print("[warn] check de fidelidad fallido: " + k, file=sys.stderr)
    if not fid["ok_global"]:
        print("[warn] F2/F3 fallida: el vectorizado NO coincide con el motor", file=sys.stderr)

    sharpe_oos_ann = ann_sharpe_monthly(net_oos)
    dsr_info = deflated_sharpe(net_oos.values.astype(float), n_trials=n_ledger)

    def _stat(r):
        v = np.asarray(r, dtype=float)
        s = v.std(ddof=1)
        return float(v.mean() / s * np.sqrt(12.0)) if s > 0 else 0.0

    ci_lo, ci_hi = circular_block_bootstrap_ci(
        net_oos.values.astype(float), _stat,
        block_size=BOOTSTRAP_BLOCK, n_bootstrap=BOOTSTRAP_REPS, confidence=0.95, seed=SEED,
    )

    cum_net = float((1.0 + net_oos).prod() - 1.0)

    if not fidelity_ok:
        verdict = "NO_INTERPRETABLE"
        verdict_txt = "Checks de fidelidad fallidos — corrida NO interpretable (pre-registro §5); NO cuenta como CUMPLE ni NO_CUMPLE de la hipotesis."
    elif sharpe_oos_ann > 0 and dsr_info.get("dsr", float("nan")) >= DSR_THRESHOLD:
        verdict = "CUMPLE"
        verdict_txt = "Sharpe_OOS > 0 Y DSR >= %.2f -> edge neto OOS fresco confirmado bajo criterio binario §5." % DSR_THRESHOLD
    else:
        verdict = "NO_CUMPLE"
        verdict_txt = "Criterio §5 no alcanzado (se requiere Sharpe_OOS>0 Y DSR>=%.2f) -> NO_CUMPLE mecanico; nada se promueve." % DSR_THRESHOLD

    lines = []
    out = lines.append
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dur = (datetime.datetime.now() - t0).total_seconds()
    out("=" * 78)
    out("VALIDACION OOS FRESCA momentum+RSI — definicion EXACTA congelada (sin re-optimizacion)")
    out("Pre-registro: PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md — criterio §5 sellado ANTES de correr")
    out("Generado: %s -> %s | duracion %.1fs" % (t0.strftime("%Y-%m-%d %H:%M:%S"),
                                                 datetime.datetime.now().strftime("%H:%M:%S"), dur))
    out("=" * 78)
    out("")
    out("--- Definicion congelada (leida del motor, no hardcodeada) ---")
    out("  pesos motor: w_mom=%.4f w_rsi=%.4f (SignalEngine.factor_weights[0])" % (w_mom, w_rsi))
    out("  score >= %.2f | rsi_score 0.8 si %d<rsi<%d sino 0.4 | gates: close>ema50>ema200," % (
        ENTRY_THRESHOLD, RSI_SCORE_BAND[0], RSI_SCORE_BAND[1]))
    out("  adx14>=%d, %d<rsi14<%d, volume_ratio>=%.1f — SIN regime-gate/BMA/stops (limitacion §7)" % (
        ADX_MIN, RSI_GATE[0], RSI_GATE[1], VR_MIN))
    out("  costos: 0.0005/lado + 0.0005 slippage = %.4f ida-y-vuelta/mes con posiciones (conv. §39/§40)" % cost_per_rebalance)
    out("  ejecucion: senal cierre ultimo habil mes m -> OPEN primer habil m+1 -> CLOSE ultimo habil m+1")
    out("")
    out("--- Ventana ---")
    out("  cache: %d simbolos, ultima fecha %s (sin descargas; updater de precios caido desde ~2026-08-15)"
        % (n_symbols_loaded, meta["cache_end_global"]))
    out("  corte IS/OOS: 2023-12-31 | OOS nominal desde %s | embargo %s descartado(s) (20 ruedas)" % (
        OOS_FIRST_MONTH, [str(x) for x in embargoed]))
    out("  mes parcial final descartado: %s" % (partial_dropped or "ninguno"))
    out("  OOS efectivo: T=%d meses (%s -> %s)" % (T_eff, eff_months[0], eff_months[-1]))
    out("")
    out("--- Checks de fidelidad (pre-registrados §2; fallar alguno -> NO_INTERPRETABLE) ---")
    out("  F1 universo 50/50: %s" % ("OK" if checks["F1_universo"]["ok"] else "FALLO"))
    for sym in FIDELITY_SAMPLES:
        rep = fid[sym]
        out("  F2/F3 %-5s max|d_score|=%.2e mism_eligible=%d rows=%d -> %s"
            % (sym, rep["max_abs_diff_score"], rep["eligible_mismatches"], rep["rows"],
               "OK" if rep["ok"] else "FALLO"))
    out("  F4 cobertura: %d/%d meses con senal (%.1f%%, min %.0f%%) -> %s"
        % (checks["F4_cobertura"]["meses_con_senal"], T_eff, coverage_ratio * 100,
           MIN_COVERAGE * 100, "OK" if checks["F4_cobertura"]["ok"] else "FALLO"))
    out("  F5 edge bruto ex-costos (meses con senal): %+.4f/mes -> %s"
        % (gross_active_mean, "OK" if checks["F5_edge_bruto"]["ok"] else "FALLO"))
    out("  F6 T minimo (%d): %d -> %s" % (MIN_T_MONTHS, T_eff, "OK" if checks["F6_T_minimo"]["ok"] else "ABORT"))
    out("  FIDELIDAD GLOBAL: %s" % ("OK" if fidelity_ok else "FALLIDA"))
    out("")
    out("--- Resultado primario (criterio §5 binario, sin zona gris) ---")
    out("  Sharpe_OOS anualizado NETO (mensual x sqrt(12), incl. meses cash): %+.4f" % sharpe_oos_ann)
    out("  Sharpe mensual (frecuencia nativa): %+.6f" % dsr_info.get("sr_monthly", float("nan")))
    out("  CI 95%% bootstrap bloques circulares (bloque=%dm, %d reps, seed %d): [%+.4f, %+.4f]"
        % (BOOTSTRAP_BLOCK, BOOTSTRAP_REPS, SEED, ci_lo, ci_hi))
    out("  Retorno acumulado neto OOS: %+.2f%%" % (cum_net * 100))
    dsr = dsr_info.get("dsr", float("nan"))
    out("  DSR Bailey&LdP2014: %.4f (N_eff=consumed_budget signal_diagnosis=%d, T=%d)"
        % (dsr, n_ledger, dsr_info["T"]))
    out("     skew=%.4f kurt_pearson=%.4f E_max=%.4f SR0=%.6f V[SR_n]=%.3e (%s)"
        % (dsr_info.get("skew", float("nan")), dsr_info.get("kurt_pearson", float("nan")),
           dsr_info.get("e_max", float("nan")), dsr_info.get("sr0", float("nan")),
           dsr_info.get("v_sr_trials_used", float("nan")), dsr_info.get("v_sr_source", "")))
    out("  Criterio: CUMPLE si Sharpe_OOS>0 Y DSR>=%.2f | cualquier otra cosa NO_CUMPLE" % DSR_THRESHOLD)
    out("")
    out("  >>> VEREDICTO MECANICO: %s <<<" % verdict)
    out("  %s" % verdict_txt)
    out("")
    out("--- Serie mensual neta OOS (mes: n_pos, bruto, neto) ---")
    for m in eff_months:
        out("  %s: n=%2d bruto=%+.4f neto=%+.4f" % (m, int(pos_oos[m]), gross_oos[m], net_oos[m]))
    out("")
    out("--- Limitaciones declaradas ANTES de correr (§7 pre-registro) ---")
    out("  1. T=30 corto -> IC ancho del Sharpe (~sqrt(12/T)); CI bootstrap obligatorio en lectura.")
    out("  2. Equal-weight mensual vectorizado vs motor completo: sin stops/barriers/regime-gate/")
    out("     sizing Kelly/caps ni BMA online — mide el EDGE de la senal congelada, no el P&L del motor.")
    out("     Un CUMPLE HABILITA un trial formal W1/W2/W3 del motor; no lo reemplaza.")
    out("  3. Costo full-rebalance conservador (0.002/mes con posiciones).")
    out("  4. Cache estancado a %s (bug updater detectado 2026-08-22); ventana termina ahi." % meta["cache_end_global"])
    out("  5. V[SR_n] proxy conservador repo Fase 0b (comparable con todos los DSR historicos).")
    out("  6. Prohibido editar criterios post-corrida; correccion metodologica = nuevo pre-registro.")
    out("")
    out("--- Reproduccion ---")
    out("  seed=%d | N_eff=%d | T=%d | trial_id=%s" % (SEED, n_ledger, T_eff, TRIAL_ID))
    txt = "\n".join(lines) + "\n"

    txt_path = os.path.join(OUT_DIR, "%s_%s.txt" % (TRIAL_ID, ts))
    json_path = os.path.join(OUT_DIR, "%s_%s.json" % (TRIAL_ID, ts))
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(txt)

    payload = {
        "trial_id": TRIAL_ID,
        "status": "EJECUTADO",
        "veredicto": verdict,
        "veredicto_txt": verdict_txt,
        "umbral_aplicado": "Sharpe_OOS>0 Y DSR>=0.95 (Bailey&LdP2014, N=ledger signal_diagnosis)",
        "sharpe_oos_annualized": float(sharpe_oos_ann),
        "ci95_bootstrap": [float(ci_lo), float(ci_hi)],
        "cum_return_net": cum_net,
        "dsr": dsr,
        "dsr_inputs": {k: v for k, v in dsr_info.items() if k != "dsr"},
        "T_meses_efectivos": int(T_eff),
        "meses_efectivos": [str(m) for m in eff_months],
        "embargo_descartado": [str(x) for x in embargoed],
        "mes_parcial_descartado": partial_dropped,
        "serie_mensual": [
            {"mes": str(m), "n_senales": int(pos_oos[m]),
             "bruto": float(gross_oos[m]), "neto": float(net_oos[m])}
            for m in eff_months
        ],
        "checks": checks,
        "fidelity_ok": fidelity_ok,
        "definicion_congelada": {
            "w_mom": w_mom, "w_rsi": w_rsi,
            "entry_threshold": ENTRY_THRESHOLD,
            "rsi_score_band": RSI_SCORE_BAND, "rsi_gate": RSI_GATE,
            "adx_min": ADX_MIN, "volume_ratio_min": VR_MIN,
            "momentum": "pct_change(252)*100, score clip((x+50)/150)",
            "cost_per_rebalance": cost_per_rebalance,
            "execution": "open(date+1) -> close(last day of month), lag 1",
        },
        "ventana": {
            "cutoff_is_oos": "2023-12-31",
            "cache_end": meta["cache_end_global"],
            "n_symbols": int(n_symbols_loaded),
        },
        "seed": SEED,
        "timestamp": ts,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(txt)
    print("\nOut: " + txt_path)
    print("Out: " + json_path)

    if verdict not in ("CUMPLE", "NO_CUMPLE"):
        print("Ledger: NO se registra — corrida %s (pre-registro §5: fidelidad fallida no "
              "consume trial de hipótesis)." % verdict)
        return 1

    register_trial({
        "id": TRIAL_ID,
        "fecha": datetime.date.today().isoformat(),
        "familia": "signal_diagnosis",
        "hipotesis": ("Baseline momentum+RSI con definicion EXACTA congelada tiene edge neto "
                      "OOS fresco (2024-02..2026-07, embargo 20 ruedas): Sharpe_OOS>0 Y DSR>=0.95"),
        "n_trials_consumidos": 1,
        "umbral_aplicado": "Sharpe_OOS>0 Y DSR>=0.95 (Bailey&LdP2014, N=ledger signal_diagnosis)",
        "veredicto": verdict,
        "artefacto": os.path.relpath(txt_path, "."),
        "seccion_doc": "PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md §5",
    })
    print("Ledger: signal_diagnosis %d->%d | id=%s | veredicto=%s"
          % (n_ledger, consumed_budget("signal_diagnosis"), TRIAL_ID, verdict))
    return 0





if __name__ == "__main__":
    sys.exit(main())
