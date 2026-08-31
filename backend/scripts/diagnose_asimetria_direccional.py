"""
PRE_REGISTRO_ASIMETRIA_DIRECCIONAL.md §2-§11 — Trial #21 (slot 28, signal_diagnosis).

Asimetría direccional: ¿el rank IC de los factores es distinto bajo impulso de alza
(UP) que bajo impulso de baja (DOWN)? Test primario: Δ_f = IC_up − IC_down (UNA
estadística por factor, Newey-West L=4, mismo estimador que §0.5a/§25/§26/§36).

Fidelidad al pre-registro (todo congelado 2026-08-30):
- Etiquetado §2: ret_impulso(i,t) = P(t-1)/P(t-1-63) - 1. Etiqueta usa SOLO precios
  hasta t-1; outcome fwd_ret(i,t) = P(t+20)/P(t) - 1. Cero solape.
- Alineación §4.1: factor_f(i,t-1) vs fwd_ret_20d(i,t) — el Spearman por fecha t
  cruza el factor MEDIDO EN t-1 con el retorno que EMPIEZA en t (lag ejecutable
  idéntico al estándar del proyecto; el factor se shifta 1 rueda hacia adelante).
- Estrato confirmatorio (signo pre-declarado §3.1):
    volume_shock Δ>0 | rsi_14 Δ>0 (degeneración, regla >1/3 §9.3) |
    momentum_12_1 Δ>0 (circularidad, Spearman reportado §9.2) | adx_14 Δ≈0 (simetría)
  Umbral |t|>2.50 (Bonferroni-4 bilateral, scipy 2.4977->2.50).
- Estrato exploratorio RMT (§3.2): los 8 factores residuales del artefacto
  rmt_mp_20260811_150849 usados como SCORE ESTÁTICO por símbolo = proyección
  loading-vector (cada F_k es una combinación lineal FIJA de los 50 símbolos:
  F_k(i) = loading(i,k)). Loadings in-sample declarados; veredicto acotado a
  candidato. Umbral |t|>2.74.
  NOTA IMPL (declarada ANTES de correr): los loadings son por-SÍMBOLO (matriz
  50x8), no por-fecha — el score F_k de un símbolo i es su peso loading(i,k),
  constante en el tiempo. El ranking intra-fecha de F_k ordena los símbolos por
  su exposición al factor residual k. Es la lectura fiel del artefacto citado
  (rmt_loadings_8factors.csv del ANALISIS_RMT de OpenCode).
- Ventanas W1/W2/W3 + TOTAL descriptivo. Gate de cobertura ANTES de cualquier IC:
  ≥75 fechas con ambos lados Y ≥10 símbolos/lado (mediana). Debajo → ventana NO
  INTERPRETABLE. 1 sola interpretable → GRIS automático (§5).
- Veredicto §7: CUMPLE si ≥1 confirmatorio |t|>2.50 en ≥2/3 interpretables, signo
  pre-declarado, |Δ|≥0.05 en las significativas, coberturas cumplidas. Si no,
  NO_CUMPLE. RMT solo puede dar GRIS-candidato (nunca CUMPLE). ADX solo puede
  dar GRIS-sorpresa (nunca CUMPLE — hipótesis de simetría).
- Robustez (X=±15%, h=5d): DESPUÉS del veredicto, solo degrada, sin test formal.
- UNA corrida, seed 42, cache-only, sin motor, sin costos (diagnóstico de panel).

Uso (desde ~/Desktop/fortress_core):
  cd backend && .venv/bin/python -m scripts.diagnose_asimetria_direccional
Salida:
  data/cache/trial21_asimetria_direccional_<ts>.txt + .json
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.indicators import calculate_all_indicators
from scipy import stats

# ----------------------------------------------------------------------------
# Parámetros congelados (§2, §3, §5, §6)
# ----------------------------------------------------------------------------
TRIAL_ID = "trial21_asimetria_direccional"
D_IMPULSO = 63                 # ventana de impulso (habiles)
X_THR = 0.10                   # umbral UP/DOWN (primaria)
H_HORIZON = 20                  # outcome fwd habiles
WARMUP_FROM = "2015-06-01"     # momentum_12_1 (252d) + ret_imp (63+1) + buffer
START, END = "2019-01-01", "2026-08-04"
MIN_SYM_PER_SIDE = 10           # piso símbolos por lado por fecha (§5)
MIN_DATES_BOTH = 75             # piso fechas con ambos lados (§5)
NW_LAGS = 4                     # Newey-West L (§4)
T_CONFIRM = 2.50                # Bonferroni-4 bilateral (§6, scipy 2.4977->2.50)
T_EXPLORE = 2.74                # Bonferroni-8 bilateral (§6, scipy 2.7344->2.74)
DELTA_MIN = 0.05                # magnitud mínima (§6, heredada §36-ii)
RSI_DEGEN_FLOOR = 0.01          # std intra-fecha del score binario < umbral = degenerado
RSI_DEGEN_MAX_FRAC = 1.0 / 3.0  # >1/3 fechas-DOWN degeneradas → Δ no interpretable (§9.3)
SEED = 42

WINDOWS = {
    "W1": ("2020-01-01", "2021-12-31"),
    "W2": ("2022-01-01", "2023-12-31"),
    "W3": ("2024-01-01", END),
}

# Estrato confirmatorio §3.1: (nombre, columna, signo esperado de Δ_f)
FACTORS_CONFIRM = [
    ("volume_shock", "volume_shock", +1),
    ("rsi_14", "rsi14", +1),
    ("momentum_12_1", "momentum_12_1", +1),
    ("adx_14", "adx14", 0),      # 0 = hipótesis de SIMETRÍA (sorpresa si ≠0)
]
RMT_COLS = [f"F{i}" for i in range(8)]

CACHE_DIR = os.path.join("data", "cache")
LOADINGS_PATH = os.path.join("data", "cache", "rmt_loadings_8factors.csv")


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """Copia FIEL de §0.5a/§25/§26/§36 (diagnose_sector_clusters.py:95)."""
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


# ----------------------------------------------------------------------------
# Panel (§2 + §3): una fila por (fecha, símbolo) con factores, etiqueta, outcome
# ----------------------------------------------------------------------------
def _load_close_frames() -> dict:
    """OHLCV por símbolo ya recortado al warmup, columnas minúsculas."""
    out = {}
    for sym in SYMBOLS:
        path = os.path.join(CACHE_DIR, f"{sym}.parquet")
        if not os.path.exists(path):
            print(f"[warn] {sym} sin parquet — excluido", file=sys.stderr)
            continue
        df = pd.read_parquet(path)
        df.columns = [c.lower() for c in df.columns]
        df = df.sort_index()
        out[sym] = df
    return out


def build_panel() -> pd.DataFrame:
    """Panel diario con: factores del motor (§3.1), scores RMT estáticos (§3.2),
    etiqueta dir (§2) y outcome fwd (§2). Factor alineado como f(i, t-1) (§4.1)."""
    raw = _load_close_frames()

    closes = pd.DataFrame({s: d["close"] for s, d in raw.items()}).sort_index()
    closes = closes[(closes.index >= WARMUP_FROM) & (closes.index <= END)]

    # ---------- etiqueta §2: dir(t) = f( P(t-1)/P(t-1-63) - 1 ) ----------
    ret_imp_t = closes / closes.shift(D_IMPULSO) - 1.0   # fila i: P(i)/P(i-63)-1
    ret_imp_shifted = ret_imp_t.shift(1)                  # fila t: P(t-1)/P(t-1-63)-1
    ret_imp_long = ret_imp_shifted.stack().rename("ret_imp").reset_index()
    ret_imp_long.columns = ["date", "symbol", "ret_imp"]
    ret_imp_long["date"] = pd.to_datetime(ret_imp_long["date"])
    ret_imp_long["dir"] = np.where(
        ret_imp_long["ret_imp"] >= X_THR, "UP",
        np.where(ret_imp_long["ret_imp"] <= -X_THR, "DOWN", "NEUTRO"))
    ret_imp_long.loc[ret_imp_long["ret_imp"].isna(), "dir"] = None

    # ---------- factores por símbolo (medidos en t-1; se alinean en el merge) ----
    frames = []
    for sym, df in raw.items():
        df = df[(df.index >= WARMUP_FROM) & (df.index <= END)]
        if len(df) < 400:
            continue
        ind = calculate_all_indicators(df)

        # volume_shock §3.1: dollar_vol(t-1)/mean(dollar_vol(t-2..t-61)).
        # Calculamos en la misma fila t: dv(t-1) / mean(dv shift(2) rolling 60)
        dvol = ind["close"] * ind["volume"]
        ind["volume_shock"] = dvol.shift(1) / dvol.shift(2).rolling(60).mean()

        ind["momentum_63d"] = ind["close"].pct_change(D_IMPULSO) * 100.0
        ind["fwd_ret_20d"] = ind["close"].shift(-H_HORIZON) / ind["close"] - 1.0
        ind["fwd_ret_5d"] = ind["close"].shift(-5) / ind["close"] - 1.0

        cols = ["rsi14", "adx14", "momentum_12_1", "momentum_63d",
                "volume_shock", "fwd_ret_20d", "fwd_ret_5d"]
        ind = ind.copy()
        ind["symbol"] = sym
        ind.index.name = "date"
        frames.append(ind.reset_index()[["date", "symbol"] + cols])

    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    # alineación §4.1: el Spearman en fecha t usa factor medido en t-1 → shift +1
    factor_cols = ["rsi14", "adx14", "momentum_12_1", "momentum_63d", "volume_shock"]
    panel = panel.sort_values(["symbol", "date"])
    for c in factor_cols:
        panel[c] = panel.groupby("symbol")[c].shift(1)

    panel = panel.merge(ret_imp_long, on=["date", "symbol"], how="left")

    # ---------- scores RMT estáticos §3.2 (loading por símbolo, constante) ------
    loadings = pd.read_csv(LOADINGS_PATH, index_col=0)     # 50 x 8
    rmt_static = loadings.rename(columns={c: c for c in RMT_COLS}).reset_index()
    rmt_static.columns = ["symbol"] + list(rmt_static.columns[1:])
    rmt_static.columns = ["symbol"] + RMT_COLS
    panel = panel.merge(rmt_static, on="symbol", how="left")

    panel = panel[(panel["date"] >= START) & (panel["date"] <= END)]
    return panel.sort_values(["date", "symbol"]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# Estadística §4
# ----------------------------------------------------------------------------
def daily_spearman_by_side(sub: pd.DataFrame, factor: str) -> dict:
    """IC_up(t), IC_down(t), d_f(t)=up-down (solo fechas con ambos lados válidos)."""
    ics_up, ics_dn, dts = [], [], []
    n_up_sym, n_dn_sym = [], []
    deg_up, deg_dn = [], []

    for _date, day in sub.groupby("date"):
        up = day[day["dir"] == "UP"].dropna(subset=[factor, "fwd_ret_20d"])
        dn = day[day["dir"] == "DOWN"].dropna(subset=[factor, "fwd_ret_20d"])
        n_up_sym.append(len(up))
        n_dn_sym.append(len(dn))

        rho_u, rho_d = np.nan, np.nan
        if len(up) >= MIN_SYM_PER_SIDE:
            # score RSI del motor: 0.8 si 45<rsi<70, si no 0.4 → degeneración §9.3
            rsi_score_u = np.where((up["rsi14"] > 45) & (up["rsi14"] < 70), 0.8, 0.4)
            deg_up.append(float(np.std(rsi_score_u)))
            rho_u = stats.spearmanr(up[factor], up["fwd_ret_20d"])[0]
        if len(dn) >= MIN_SYM_PER_SIDE:
            rsi_score_d = np.where((dn["rsi14"] > 45) & (dn["rsi14"] < 70), 0.8, 0.4)
            deg_dn.append(float(np.std(rsi_score_d)))
            rho_d = stats.spearmanr(dn[factor], dn["fwd_ret_20d"])[0]

        if np.isfinite(rho_u):
            ics_up.append(rho_u)
        if np.isfinite(rho_d):
            ics_dn.append(rho_d)
        if np.isfinite(rho_u) and np.isfinite(rho_d):
            dts.append(rho_u - rho_d)

    def stats_(arr):
        arr = np.array(arr)
        if len(arr) == 0:
            return {"n": 0, "mean": np.nan, "se": np.nan, "t": np.nan}
        mean = float(arr.mean())
        se = newey_west_se(arr, NW_LAGS)
        return {"n": int(len(arr)), "mean": mean, "se": se,
                "t": mean / se if se > 0 else np.nan}

    return {
        "ic_up": stats_(ics_up), "ic_dn": stats_(ics_dn), "delta": stats_(dts),
        "n_dates_both": len(dts),
        "median_sym_up": float(np.median(n_up_sym)) if n_up_sym else 0.0,
        "median_sym_dn": float(np.median(n_dn_sym)) if n_dn_sym else 0.0,
        "frac_degen_up": (float(np.mean(np.array(deg_up) < RSI_DEGEN_FLOOR))
                          if deg_up else np.nan),
        "frac_degen_dn": (float(np.mean(np.array(deg_dn) < RSI_DEGEN_FLOOR))
                          if deg_dn else np.nan),
    }


def rsi_delta_interpretable(res: dict) -> bool:
    """§9.3: >1/3 de fechas-DOWN degeneradas → Δ de RSI no interpretable en la ventana."""
    f = res.get("frac_degen_dn")
    return not (np.isfinite(f) and f > RSI_DEGEN_MAX_FRAC)


def gate_window(panel_slice: pd.DataFrame) -> dict:
    """Gate de cobertura §5 — corre ANTES de mirar cualquier resultado."""
    cov = panel_slice.dropna(subset=["ret_imp", "fwd_ret_20d"])
    both = 0
    med_ups, med_dns = [], []
    for _d, day in cov.groupby("date"):
        nu = int((day["dir"] == "UP").sum())
        nd = int((day["dir"] == "DOWN").sum())
        med_ups.append(nu)
        med_dns.append(nd)
        if nu >= MIN_SYM_PER_SIDE and nd >= MIN_SYM_PER_SIDE:
            both += 1
    mu = float(np.median(med_ups)) if med_ups else 0.0
    md = float(np.median(med_dns)) if med_dns else 0.0
    ok = both >= MIN_DATES_BOTH and mu >= MIN_SYM_PER_SIDE and md >= MIN_SYM_PER_SIDE
    return {"n_dates_both": both, "median_sym_up": mu, "median_sym_dn": md, "ok": ok}


def main() -> int:
    t0 = datetime.datetime.now()
    np.random.seed(SEED)
    ts = t0.strftime("%Y%m%d_%H%M%S")
    out_txt = os.path.join(CACHE_DIR, f"{TRIAL_ID}_{ts}.txt")
    out_json = os.path.join(CACHE_DIR, f"{TRIAL_ID}_{ts}.json")

    def out(msg: str = ""):
        print(msg, flush=True)
        with open(out_txt, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("PRE_REGISTRO_ASIMETRIA_DIRECCIONAL §2-§11 — Trial #21 (slot 28, signal_diagnosis)")
    out(f"Congelado 2026-08-30 | corrida única {t0:%Y-%m-%d %H:%M:%S} | seed 42 | cache-only")
    out(f"Etiquetado §2: ret_impulso=P(t-1)/P(t-1-{D_IMPULSO})-1, UP≥+{X_THR:.0%}, "
        f"DOWN≤-{X_THR:.0%} | outcome h={H_HORIZON}d | factor alineado f(i,t-1) §4.1")
    out(f"Umbrales scipy congelados §6: confirmatorio |t|>{T_CONFIRM:.2f} (B4 bilateral), "
        f"RMT |t|>{T_EXPLORE:.2f} (B8 bilateral), |Δ|≥{DELTA_MIN}")
    out(f"Gate cobertura §5: ≥{MIN_DATES_BOTH} fechas ambos lados, "
        f"≥{MIN_SYM_PER_SIDE} símb/lado (mediana)")
    out("Ventanas: " + ", ".join(f"{k} {v[0]}->{v[1]}" for k, v in WINDOWS.items()))
    out("=" * 78)

    out("\nCargando panel diario (indicadores del motor, etiqueta §2, RMT estático §3.2)...")
    panel = build_panel()
    out(f"Panel: {len(panel)} filas | {panel['date'].nunique()} fechas | "
        f"{panel['symbol'].nunique()} símbolos")
    out(f"Rango: {panel['date'].min().date()} -> {panel['date'].max().date()}")
    dist = panel["dir"].value_counts(dropna=True)
    out("Etiqueta dir: " + ", ".join(f"{k}={int(v)}" for k, v in dist.items()))

    all_factors = [c for (_, c, _) in FACTORS_CONFIRM] + RMT_COLS

    # ================= GATE DE COBERTURA (§5 — antes de cualquier IC) ==============
    out("\n" + "=" * 78)
    out("GATE DE COBERTURA PRE-RESULTADO (§5) — sin IC antes de este cuadro")
    out(f"{'ventana':9s} {'fechas':>7s} {'UP(med)':>8s} {'DOWN(med)':>9s} {'interpretable':>13s}")
    gate = {}
    for wname, (ws, we) in WINDOWS.items():
        sub = panel[(panel["date"] >= ws) & (panel["date"] <= we)]
        g = gate_window(sub)
        gate[wname] = g
        out(f"{wname:9s} {g['n_dates_both']:7d} {g['median_sym_up']:8.1f} "
            f"{g['median_sym_dn']:9.1f} {'SI' if g['ok'] else 'NO INTERPRETABLE':>13s}")

    n_interp = sum(1 for v in gate.values() if v["ok"])
    out(f"\nVentanas interpretables: {n_interp}/3 (regla §5: 1 sola → GRIS automático)")

    if n_interp == 0:
        out("\nVEREDICTO MECÁNICO: GRIS — ninguna ventana interpretable (cobertura §5).")
        out("Nada se integra. Decisión de Boris (§7 GRIS-a).")
        _write_json(out_json, "GRIS", "ninguna ventana interpretable por cobertura §5",
                    {}, out_txt, ts, gate=gate)
        out(f"\nOut: {out_txt}")
        out(f"Out: {out_json}")
        print(f"\n[done] veredicto=GRIS (cobertura) — {os.path.basename(out_txt)}")
        return 0

    # ================= ICs POR LADO + Δ (§4) =====================================
    results = {}
    for wname, (ws, we) in WINDOWS.items():
        sub = panel[(panel["date"] >= ws) & (panel["date"] <= we)]
        out("\n" + "=" * 78)
        out(f"--- {wname} {ws} -> {we} "
            f"({gate[wname]['n_dates_both']} fechas ambos lados) ---")
        out(f"{'factor':14s} {'n_up':>5s} {'IC_up':>8s} {'t_up':>7s} {'n_dn':>5s} "
            f"{'IC_dn':>8s} {'t_dn':>7s} {'n_both':>6s} {'Δ_f':>8s} {'SE':>7s} {'t_f':>7s}")
        wres = {}
        for f in all_factors:
            res = daily_spearman_by_side(sub, f)
            wres[f] = res
            d, ru, rd = res["delta"], res["ic_up"], res["ic_dn"]
            out(f"{f:14s} {ru['n']:5d} {ru['mean']:+8.4f} {ru['t']:+7.2f} {rd['n']:5d} "
                f"{rd['mean']:+8.4f} {rd['t']:+7.2f} {d['n']:6d} "
                f"{d['mean']:+8.4f} {d['se']:7.4f} {d['t']:+7.2f}")
        results[wname] = wres

        # métricas obligatorias de mecanismo (§3.1/§9)
        if "rsi_14" in wres:
            r = wres["rsi_14"]
            fu = r["frac_degen_up"] if np.isfinite(r["frac_degen_up"]) else float("nan")
            fd = r["frac_degen_dn"] if np.isfinite(r["frac_degen_dn"]) else float("nan")
            out(f"  RSI degeneración (std score<0.01): UP={fu:.2%} DOWN={fd:.2%} "
                f"(§9.3: DOWN>33.3% → Δ_rsi NO interpretable aquí)")
        msub = sub.dropna(subset=["momentum_63d", "ret_imp"])
        if len(msub) > 30:
            rho, _ = stats.spearmanr(msub["momentum_63d"], msub["ret_imp"])
            out(f"  Circularidad §9.2: Spearman(mom_63d, ret_impulso) = {rho:+.4f} "
                f"(momentum_12_1 comparte {D_IMPULSO}d con la etiqueta)")

    # TOTAL descriptivo (sin gate, informativo §5)
    out("\n" + "=" * 78)
    out("--- TOTAL 2019->2026 (DESCRIPTIVO, sin gate, informativo) ---")
    sub = panel[(panel["date"] >= START) & (panel["date"] <= END)]
    for f in all_factors:
        d = daily_spearman_by_side(sub, f)["delta"]
        out(f"{f:14s} Δ={d['mean']:+.4f} t={d['t']:+7.2f} (n={d['n']})")

    # ================= VEREDICTO MECÁNICO (§7) ====================================
    out("\n" + "=" * 78)
    out(f"VEREDICTO MECÁNICO §7 — confirmatorio |t|>{T_CONFIRM:.2f}, |Δ|≥{DELTA_MIN}, "
        f"≥2/3 de {n_interp} interpretables, signo pre-declarado §3.1")

    interpret_windows = [w for w in WINDOWS if gate[w]["ok"]]
    cumple_factors, gris_reasons, exploratory_hits = [], [], []

    for fname, col, signo in FACTORS_CONFIRM:
        wins, sig_windows, blocked_rsi = 0, [], []
        for w in interpret_windows:
            res = results[w][col]
            d = res["delta"]
            if fname == "rsi_14" and not rsi_delta_interpretable(res):
                blocked_rsi.append(w)
                continue
            if not (np.isfinite(d["t"]) and abs(d["t"]) > T_CONFIRM
                    and abs(d["mean"]) >= DELTA_MIN):
                continue
            if fname == "adx_14":
                # simetría pre-declarada: pasar es SORPRESA → GRIS, no confirmación
                gris_reasons.append(
                    f"adx_14 SORPRESA (simetría refutada): {w} t={d['t']:+.2f} "
                    f"Δ={d['mean']:+.4f}")
                continue
            if (signo > 0 and d["mean"] <= 0) or (signo < 0 and d["mean"] >= 0):
                continue
            wins += 1
            sig_windows.append(w)
        if wins >= 2:
            cumple_factors.append((fname, sig_windows))
        if blocked_rsi:
            gris_reasons.append(
                f"rsi_14 Δ no-interpretable en {','.join(blocked_rsi)} "
                f"(>1/3 DOWN degenerado, §9.3)")

    for f in RMT_COLS:
        wins = 0
        for w in interpret_windows:
            d = results[w][f]["delta"]
            if np.isfinite(d["t"]) and abs(d["t"]) > T_EXPLORE and abs(d["mean"]) >= DELTA_MIN:
                wins += 1
        if wins >= 2:
            exploratory_hits.append(f)
            gris_reasons.append(
                f"{f} pasa umbral exploratorio (candidato OOS rolling — nunca CUMPLE, §3.2)")

    if cumple_factors and n_interp >= 2:
        verdict = "CUMPLE"
        detail = "; ".join(f"{f} en {','.join(ws)}" for f, ws in cumple_factors)
        reason = (f"confirmatorio con |t|>{T_CONFIRM} y |Δ|≥{DELTA_MIN} en ≥2/3: {detail}")
    elif n_interp == 1:
        verdict = "GRIS"
        reason = "solo 1 ventana interpretable (§5) — GRIS automático, decisión de Boris"
    elif gris_reasons:
        verdict = "GRIS"
        reason = "; ".join(gris_reasons[:6])
    else:
        verdict = "NO_CUMPLE"
        reason = (f"ningún factor confirmatorio alcanza |t|>{T_CONFIRM:.2f} con "
                  f"|Δ|≥{DELTA_MIN} en ≥2/3 ventanas interpretables — condicionar por "
                  f"dirección NO rescata señal; la debilidad pooled no es artefacto "
                  f"del pooling")

    out(f"\nEstrato confirmatorio: {len(cumple_factors)} factor(es) cumplen")
    out(f"Estrato exploratorio RMT: {len(exploratory_hits)} candidato(s) "
        f"({', '.join(exploratory_hits) or 'ninguno'})")
    if gris_reasons:
        out("Motivos GRIS declarados:")
        for r in gris_reasons:
            out(f"  - {r}")
    out(f"\nVEREDICTO: {verdict}")
    out(f"Nota: {reason}")
    post = ("CUMPLE → integración requiere trial motor_signal propio (DSR≥0.90)."
           if verdict == "CUMPLE" else
           ("NO_CUMPLE → línea asimetría cerrada; siguiente frente = rama W2 §9 "
            "(basket/rotación con RMT como generadoras)." if verdict == "NO_CUMPLE" else
            "GRIS → nada se integra; listar qué falta para desempatar."))
    out(f"Condicional post-veredicto (§8): {post}")

    # ============ ROBUSTEZ DESCRIPTIVA (§2.3 — después del veredicto) ============
    out("\n" + "=" * 78)
    out("ROBUSTEZ DESCRIPTIVA (§2.3 — solo degrada, sin test formal, sin consumo)")
    out(f"{'variante':12s} {'factor':14s} {'Δ':>8s} {'t':>7s} {'n':>5s}")
    robustez = {}
    for label in ("X=±15%", "h=5d"):
        if label == "X=±15%":
            p2 = panel.copy()
            p2["dir"] = np.where(p2["ret_imp"] >= 0.15, "UP",
                                 np.where(p2["ret_imp"] <= -0.15, "DOWN", "NEUTRO"))
            p2.loc[p2["ret_imp"].isna(), "dir"] = None
        else:
            p2 = panel.copy()
            p2["fwd_ret_20d"] = p2["fwd_ret_5d"]
        for fname, col, _s in FACTORS_CONFIRM:
            sub = p2[(p2["date"] >= START) & (p2["date"] <= END)]
            d = daily_spearman_by_side(sub, col)["delta"]
            robustez[f"{label}|{fname}"] = {"mean": d["mean"], "t": d["t"], "n": d["n"]}
            out(f"{label:12s} {fname:14s} {d['mean']:+8.4f} {d['t']:+7.2f} {d['n']:5d}")

    # ============ NIVEL 2 DESCRIPTIVO (§3.3 — solo sobrevivientes) ==============
    out("\n" + "=" * 78)
    out("NIVEL 2 (§3.3) — descriptivo, sin test, sin presupuesto")
    survivors = [fn for (fn, _c, _s) in FACTORS_CONFIRM
                 if any(fn == cf for cf, _ in cumple_factors)] + exploratory_hits
    if survivors:
        out(f"Sobrevivientes nivel 1: {', '.join(survivors)} — desglose por régimen "
            "HMM/VIX queda como pendiente descriptivo a pedido de Boris; no "
            "bloquea el veredicto.")
    else:
        out("Sin sobrevivientes nivel 1 — nada que desglosar.")

    _write_json(out_json, verdict, reason, results, out_txt, ts,
                cumple_factors=[f for f, _ in cumple_factors],
                exploratory_hits=exploratory_hits, gate=gate, robustez=robustez)

    out(f"\nOut: {out_txt}")
    out(f"Out: {out_json}")
    out(f"Ledger: completar reserva {TRIAL_ID} con veredicto={verdict} (Track A).")
    print(f"\n[done] veredicto={verdict} — artefacto {os.path.basename(out_txt)}")
    return 0


def _write_json(path, verdict, reason, results, out_txt, ts,
                cumple_factors=None, exploratory_hits=None, gate=None, robustez=None):
    payload = {
        "ts": ts, "id": TRIAL_ID, "familia": "signal_diagnosis",
        "veredicto": verdict, "razon": reason,
        "parametros": {
            "D_impulso": D_IMPULSO, "X": X_THR, "h": H_HORIZON,
            "t_confirm": T_CONFIRM, "t_explore": T_EXPLORE,
            "delta_min": DELTA_MIN, "nw_lags": NW_LAGS,
            "min_sym_per_side": MIN_SYM_PER_SIDE, "min_dates_both": MIN_DATES_BOTH,
        },
        "cumple_factors": cumple_factors or [],
        "exploratory_hits": exploratory_hits or [],
        "gate_cobertura": gate or {},
        "robustez": robustez or {},
        "artefacto": os.path.relpath(out_txt, "."),
    }
    if results:
        payload["results"] = {
            w: {f: {k: v for k, v in r.items()} for f, r in wf.items()}
            for w, wf in results.items()
        }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    sys.exit(main())
