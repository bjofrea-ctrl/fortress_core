"""
PLAN_MEJORA_MATEMATICA §41 (2026-08-22) — Tarea O: Frog-in-the-Pan.
Information Discreteness (Da-Gurun-Warachka 2014 RFS) condicionando momentum_12_1.

Test pre-registrado en §41, escrito ANTES de correr. Familia signal_diagnosis,
n_trials=23 (22 consumidos + 1), umbral Bonferroni bilateral:
   |t| > z(1 - 0.05/46) = 3.065

HIPÓTESIS: el rank IC cross-sectional de momentum_12_1 vs fwd_20 es MAYOR en el
tercil de MENOR ID (información continua) que en el de MAYOR ID (discreta).
   ID = sign(PRET) × (%neg − %pos), ventana de formación = los mismos 252 días
   hábiles que momentum_12_1 (= close.pct_change(252)); días con retorno 0
   excluidos de ambas fracciones. Todo causal (solo retornos ≤ t).

MÉTODO (protocolo estándar de la familia, §25/§37/§38):
   - Panel: universo 50, sin máscara de elegibilidad.
   - Terciles de ID POR FECHA (qcut cross-sectional causal): tercil 1 = menor ID
     (continua), tercil 3 = mayor ID (discreta). Mínimo 5 símbolos/bucket/día.
   - IC diario = Spearman intra-bucket por fecha vs fwd_20.
   - ΔIC_t = IC_tercil1_t − IC_tercil3_t (serie pareada: solo fechas con ambos
     buckets computables). SE Newey-West L = min(12, n_dias//8).
   - Ventanas W1 2020-2021, W2 2022-2023, W3 2024->2026-07-06.

CRITERIO (pre-registrado en §41, UN slot en el ledger):
   ΔIC > 0 con t_NW > +3.065 en >= 2/3 ventanas -> CUMPLE.
   ICs por tercil y TOTAL se reportan pero NO disparan veredicto.

Reglas: Python 3.9 real (backend/.venv). Lee el cache, no descarga nada.
No toca indicators.py/signal_engine.py/trial_registry.py/market.py/live.py/predict.py.
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
DATA_END = "2026-08-21"
MIN_SYMBOLS = 5

# Umbral Bonferroni de la familia signal_diagnosis (n_trials=23, dos colas)
ALPHA_PER = 0.05 / (2 * 23)
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))  # 3.065

WINDOWS = {
    "W1": (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
    "W2": (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31")),
    "W3": (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-07-06")),
}

FORMATION_DAYS = 252  # misma ventana que momentum_12_1 (close.pct_change(252))


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


def daily_ics(panel: pd.DataFrame, factor: str, target: str,
              min_sym: int = MIN_SYMBOLS) -> dict:
    """Spearman por fecha (ranks sobre símbolos de ESA fecha) factor vs target,
    separado por tercil de ID asignado esa fecha. Devuelve {bucket: {date: ic}}."""
    ics_by_bucket = {}
    for _date, day in panel.groupby("date"):
        for bucket, d in day.groupby("id_tercil"):
            d = d[[factor, target]].dropna()
            if len(d) < min_sym:
                continue
            rho, _ = stats.spearmanr(d[factor], d[target])
            if np.isfinite(rho):
                ics_by_bucket.setdefault(bucket, {})[_date] = rho
    return ics_by_bucket


def paired_delta_series(ics_by_bucket: dict) -> pd.Series:
    """ΔIC_t = IC_tercil1_t − IC_tercil3_t, solo fechas con AMBOS buckets."""
    lo = ics_by_bucket.get(1, {})
    hi = ics_by_bucket.get(3, {})
    common = sorted(set(lo) & set(hi))
    return pd.Series({d: lo[d] - hi[d] for d in common})


def rank_ic_stats(ics: np.ndarray, lags: int) -> dict:
    n = len(ics)
    if n == 0:
        return {"n_days": 0, "mean_ic": np.nan, "se_nw": np.nan, "t": np.nan}
    mean_ic = float(np.mean(ics))
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(n), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def build_panel() -> pd.DataFrame:
    price_data = load_universe(SYMBOLS, START, DATA_END)
    frames = []
    for sym, df in price_data.items():
        ind = calculate_all_indicators(df)
        if ind.empty:
            continue
        ind = ind.copy()
        # ID sobre la MISMA ventana de formación que momentum_12_1 (252d):
        # %neg/%pos sobre retornos diarios; días r==0 excluidos de ambas.
        ret = ind["close"].pct_change()
        neg = (ret < 0).rolling(FORMATION_DAYS).sum()
        pos = (ret > 0).rolling(FORMATION_DAYS).sum()
        nonzero = neg + pos
        pct_neg = neg / nonzero
        pct_pos = pos / nonzero
        pret_sign = np.sign(ind["momentum_12_1"])
        ind["id_disc"] = pret_sign * (pct_neg - pct_pos)

        need = ["momentum_12_1", "id_disc", "fwd_20"]
        ind["fwd_20"] = ind["close"].shift(-20) / ind["close"] - 1
        ind = ind.dropna(subset=need)
        if ind.empty:
            continue
        ind["symbol"] = sym
        ind.index.name = "date"
        frames.append(ind.reset_index()[["date", "symbol"] + need])
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    # Terciles de ID por fecha (cross-sectional, causal): 1=menor ID (continua),
    # 3=mayor ID (discreta). ranks method='first' para cortes deterministas.
    def _terciles(g):
        g = g.copy()
        if len(g) < 3 * MIN_SYMBOLS:
            g["id_tercil"] = np.nan
            return g
        g["id_tercil"] = pd.qcut(g["id_disc"].rank(method="first"), 3, labels=[1, 2, 3])
        return g

    panel = panel.groupby("date", group_keys=False).apply(_terciles)
    panel["id_tercil"] = pd.to_numeric(panel["id_tercil"], errors="coerce")
    return panel.sort_values("date").reset_index(drop=True)


def main() -> int:
    out_path = os.path.join(
        "data", "cache",
        f"trial_frog_in_the_pan_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §41 — Tarea O: Frog-in-the-Pan (ID × momentum_12_1)")
    out(f"Umbral familia signal_diagnosis (n=23, dos colas): |t| > {THRESHOLD:.3f}")
    out("Ventanas: " + ", ".join(f"{k} {v[0].date()}->{v[1].date()}" for k, v in WINDOWS.items()))
    out("ID = sign(mom_12_1) x (%neg-%pos), ventana formacion 252d; terciles por fecha")
    out("CRITERIO: deltaIC(t1-t3) > 0 con t_NW > +%.3f en >= 2/3 ventanas" % THRESHOLD)
    out("=" * 78)

    panel = build_panel()
    out(f"\nPanel: {len(panel)} filas | {panel['date'].nunique()} fechas | "
        f"{panel['symbol'].nunique()} símbolos")
    out(f"Rango fechas: {panel['date'].min().date()} -> {panel['date'].max().date()}")

    # Sanity check distribución de ID (informativo)
    q = panel["id_disc"].quantile([0.10, 0.50, 0.90])
    out("\nDistribución ID (sanity): p10=%+.4f p50=%+.4f p90=%+.4f"
        % (q.iloc[0], q.iloc[1], q.iloc[2]))

    def window_stats(sub):
        ics_b = daily_ics(sub, "momentum_12_1", "fwd_20")
        res = {}
        for b in (1, 2, 3):
            arr = np.array(list(ics_b.get(b, {}).values()))
            L = min(12, len(arr) // 8) if len(arr) else 0
            res[b] = (rank_ic_stats(arr, L), L)
        delta = paired_delta_series(ics_b)
        arr = delta.values
        L = min(12, len(arr) // 8) if len(arr) else 0
        res["delta"] = (rank_ic_stats(arr, L), L)
        res["_n_delta_days"] = len(delta)
        return res

    results = {}  # {window: res}
    out("\nRank IC por tercil de ID y ventana (signo esperado del factor: +1)")
    header = f"{'métrica':16s} {'ventana':7s} {'n_dias':>6s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s}"
    out(header)
    out("-" * len(header))
    for name, (start, end) in WINDOWS.items():
        w = panel[(panel["date"] >= start) & (panel["date"] <= end)]
        res = window_stats(w)
        results[name] = res
        for label, key in (("tercil1 (cont)", 1), ("tercil2", 2),
                           ("tercil3 (disc)", 3), ("DELTA t1-t3", "delta")):
            r, L = res[key]
            out(f"{label:16s} {name:7s} {r['n_days']:6d} {r['mean_ic']:+9.4f} "
                f"{r['se_nw']:8.4f} {r['t']:+7.2f} {L:3d}")
        out(f"{'  (dias pareados)':16s} {name:7s} {res['_n_delta_days']:6d}")

    # TOTAL pooled (solo informativo, NO pre-registrado)
    out("\nTOTAL pooled (solo informativo, NO pre-registrado)")
    res_total = window_stats(panel)
    for label, key in (("tercil1 (cont)", 1), ("tercil3 (disc)", 3), ("DELTA t1-t3", "delta")):
        r, L = res_total[key]
        out(f"{label:16s} {'TOTAL':7s} {r['n_days']:6d} {r['mean_ic']:+9.4f} "
            f"{r['se_nw']:8.4f} {r['t']:+7.2f} {L:3d}")

    # Veredicto: DELTA con t_NW > +THRESHOLD en >= 2/3 ventanas
    n_sig = sum(
        1 for res in results.values()
        if np.isfinite(res["delta"][0]["t"]) and res["delta"][0]["t"] > THRESHOLD
    )
    cumple = n_sig >= 2
    out("\n" + "=" * 78)
    out(f"CRITERIO §41: ΔIC(t1−t3) > 0 con t_NW > +{THRESHOLD:.3f} en ≥2/3 ventanas")
    sigs = [n for n, res in results.items()
            if np.isfinite(res["delta"][0]["t"]) and res["delta"][0]["t"] > THRESHOLD]
    out(f"Ventanas SIG+ de DELTA: {n_sig}/3 {sigs} -> "
        f"{'CUMPLE' if cumple else 'NO_CUMPLE'}")
    out("=" * 78)
    out(f"\nOut: {out_path}")
    print(f"\nARTIFACT:{out_path}")
    print(f"VEREDICTO:{'CUMPLE' if cumple else 'NO_CUMPLE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
