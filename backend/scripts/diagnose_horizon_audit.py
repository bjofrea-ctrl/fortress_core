"""
PLAN_MEJORA_MATEMATICA §21 (M1) — AUDITORIA DE HORIZONTE (2026-08-13).
PRE-REGISTRADO antes de correr.

Motivo (AUDITORIA_MECANICA.md, hallazgo 2): TODA la investigacion de senal de este
proyecto midio poder predictivo a 20 dias (HORIZON=20 en diagnose_rr2_intraday.py,
diagnose_ma200_clusters.py, diagnose_donchian_intraday.py, diagnose_rr2_subperiodos.py,
diagnose_regime_volatility.py, diagnose_ma200_beta_control.py). Pero el motor real NO
sostiene 20 dias: sobre el parquet de trades del baseline oficial
(baseline_clean_20260811_150643_trades.parquet, 286 operaciones) la tenencia mediana
es 11 dias, el 49.0% de las operaciones cierra en <=10 dias, y solo el 25.5% llega a
durar >=20 dias.

Es decir: medimos si los factores predicen el retorno a 20d mientras el motor cierra
la mitad de sus posiciones antes de los 10d. Nunca se midio el horizonte en el que el
sistema realmente opera.

Pregunta: los factores del motor (momentum, rsi, adx) tienen poder de seleccion
intra-dia a 5d y 10d, horizontes que SI corresponden a la tenencia real?

Metodologia: identica a diagnose_rr2_intraday.py (rank IC INTRA-DIA por fecha,
Spearman entre simbolos disponibles ese dia, promedio sobre fechas con SE
Newey-West). Unico cambio: el target. Se reusa el panel limpio ya construido
(factores + eligible ya calculados correctamente) y se le agregan los retornos
forward a 5d y 10d calculados desde precios.
  - Lags Newey-West escalados por horizonte: L = ceil(H / stride), stride=5d habiles.
    (5d -> L=1, 10d -> L=2, 20d -> L=4, igual que el original para 20d).
  - CHECK DE FIDELIDAD: el fwd_20d recalculado acá debe coincidir con la columna
    fwd_return_20d del panel. Si no coincide, el calculo de forwards esta mal y el
    resultado de 5d/10d no es confiable -> se aborta sin interpretar.

Criterio pre-registrado (sin conocer el resultado):
  - Hipotesis NUEVAS: 3 factores (momentum_score, rsi_score, adx_score) x 2
    horizontes nuevos (5d, 10d) = 6 tests. trend_score se excluye del conteo porque
    es constante dentro de la poblacion elegible (no produce test, da nan — verificado
    en §0.5a y §15). El horizonte 20d se reporta como REFERENCIA (ya testeado en
    §0.5a), NO cuenta como test nuevo.
  - Bonferroni-6, umbral |t| > 2.64 (two-sided, alpha familiar 0.05/6), con signo
    esperado positivo (mayor score -> mayor retorno).
  - VEREDICTO: si algun factor es significativo a 5d o 10d con signo esperado, el
    horizonte importa y varias refutaciones previas deben revisarse en el horizonte
    correcto. Si ninguno lo es, se cierra la duda: los factores no tienen poder de
    seleccion en NINGUN horizonte relevante, y todos los rechazos previos se refuerzan.

El script NO decide nada por si mismo mas que aplicar este criterio mecanicamente.
Ver regla §3.4: todo numero se verifica contra el artefacto.
"""
import datetime
import glob
import math
import os

import numpy as np
import pandas as pd
from scipy import stats

from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
FACTORS = {"momentum_score": +1, "rsi_score": +1, "adx_score": +1}
HORIZONS_NUEVOS = [5, 10]
HORIZONTE_REFERENCIA = 20
STRIDE_DAYS = 5
MIN_SYMBOLS = 5
N_TESTS_NUEVOS = len(FACTORS) * len(HORIZONS_NUEVOS)  # 3 x 2 = 6
Z_BONFERRONI = float(stats.norm.ppf(1 - (0.05 / N_TESTS_NUEVOS) / 2))
TOL_FIDELIDAD = 1e-6


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """Identico a diagnose_rr2_intraday.py."""
    n = len(z)
    if n < 3:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    lag_max = min(lags, n - 2)
    if lag_max < 1:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (lags + 1)
    denom = 1 + 2 * np.sum(w * rho)
    n_eff = n / max(denom, 1.0)
    return float(np.std(z, ddof=1) / np.sqrt(n_eff))


def build_forwards(price_data: dict, horizons: list) -> pd.DataFrame:
    """Retornos forward por simbolo a cada horizonte (dias HABILES = filas)."""
    rows = []
    for sym, df in price_data.items():
        d = df.sort_index()
        close = d["close"]
        out = {"date": d.index, "symbol": sym}
        for h in horizons:
            out[f"fwd_{h}"] = (close.shift(-h) / close - 1).to_numpy()
        rows.append(pd.DataFrame(out))
    return pd.concat(rows, ignore_index=True)


def intraday_rank_ic(panel: pd.DataFrame, factor: str, target: str, lags: int) -> dict:
    daily_ics = []
    for date in panel["date"].unique():
        day = panel[panel["date"] == date]
        day = day[day[factor].notna() & day[target].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day[factor], day[target])
        if np.isfinite(rho):
            daily_ics.append(rho)
    ics = np.array(daily_ics)
    if len(ics) == 0:
        return {"n_days": 0, "mean_ic": float("nan"), "se_nw": float("nan"), "t": float("nan")}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(len(ics)), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def main():
    out_path = os.path.join("data", "cache",
                            f"horizon_audit_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 78)
    log("§21 (M1) — AUDITORIA DE HORIZONTE: rank IC intra-dia a 5d/10d vs 20d — PRE-REGISTRADO")
    log("Motivo: tenencia real mediana 11d, 49% de trades cierra <=10d, solo 25.5% llega a 20d")
    log("        pero TODA la investigacion previa midio a 20d (AUDITORIA_MECANICA.md hallazgo 2)")
    log(f"Tests NUEVOS: {len(FACTORS)} factores x {len(HORIZONS_NUEVOS)} horizontes = {N_TESTS_NUEVOS}")
    log(f"Bonferroni-{N_TESTS_NUEVOS} | umbral |t| > {Z_BONFERRONI:.2f} | signo esperado +")
    log(f"20d se reporta como REFERENCIA (ya testeado en §0.5a), no cuenta como test nuevo")
    log("=" * 78)

    path = latest_panel()
    panel = pd.read_parquet(path)
    panel["date"] = pd.to_datetime(panel["date"])
    elig = panel[panel["eligible"]].copy()
    log(f"\nPanel: {os.path.basename(path)} | filas eligible: {len(elig)} | fechas: {elig['date'].nunique()}")

    log(f"Cargando precios ({len(SYMBOLS)} simbolos) para calcular forwards...")
    price_data = load_universe(SYMBOLS, START, END)
    fwd = build_forwards(price_data, HORIZONS_NUEVOS + [HORIZONTE_REFERENCIA])
    fwd["date"] = pd.to_datetime(fwd["date"])

    merged = elig.merge(fwd, on=["date", "symbol"], how="left")

    # --- CHECK DE FIDELIDAD (pre-registrado): fwd_20 recalculado vs columna del panel ---
    comp = merged[merged["fwd_return_20d"].notna() & merged["fwd_20"].notna()]
    diff = (comp["fwd_return_20d"] - comp["fwd_20"]).abs()
    max_diff = float(diff.max()) if len(diff) else float("nan")
    n_comp = len(comp)
    fidelidad_ok = (n_comp > 0) and (max_diff < TOL_FIDELIDAD)
    log(f"\n--- CHECK DE FIDELIDAD (§14) ---")
    log(f"fwd_20 recalculado vs fwd_return_20d del panel: n={n_comp} | max |dif| = {max_diff:.3e} "
        f"(tolerancia {TOL_FIDELIDAD:.0e})")
    log(f"FIDELIDAD: {'OK -> se evalua' if fidelidad_ok else 'FALLA -> NO se interpreta'}")
    if not fidelidad_ok:
        log("\nAbortado por fidelidad: el calculo de forwards no reproduce el panel, "
            "los resultados a 5d/10d no serian confiables.")
        log(f"\nOut: {out_path}")
        return

    log(f"\n{'factor':16s} {'horiz':>6s} {'tipo':>10s} {'n_days':>7s} {'mean_IC':>9s} "
        f"{'SE_NW':>8s} {'t':>7s} {'sig(Bonf)':>10s}")
    hallazgos = []
    for factor, sign in FACTORS.items():
        for h in HORIZONS_NUEVOS + [HORIZONTE_REFERENCIA]:
            lags = int(np.ceil(h / STRIDE_DAYS))
            res = intraday_rank_ic(merged, factor, f"fwd_{h}", lags)
            es_nuevo = h in HORIZONS_NUEVOS
            sig = (es_nuevo and not math.isnan(res["t"])
                   and abs(res["t"]) > Z_BONFERRONI and np.sign(res["mean_ic"]) == sign)
            if sig:
                hallazgos.append((factor, h, res))
            tipo = "NUEVO" if es_nuevo else "referencia"
            marca = str(sig) if es_nuevo else "—"
            log(f"{factor:16s} {h:5d}d {tipo:>10s} {res['n_days']:7d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {marca:>10s}")

    log(f"\n--- VEREDICTO (§21, pre-registrado) ---")
    if hallazgos:
        log(f"=> {len(hallazgos)} hallazgo(s) significativo(s) en horizontes cortos:")
        for factor, h, res in hallazgos:
            log(f"   {factor} a {h}d: IC {res['mean_ic']:+.4f}, t-NW {res['t']:+.2f}")
        log("HORIZONTE: IMPORTA — hay poder de seleccion a horizonte corto que el test a 20d")
        log("           no capturaba. Las refutaciones previas deben revisarse en el horizonte")
        log("           correcto antes de darlas por definitivas.")
    else:
        log("=> Ningun factor es significativo a 5d ni a 10d (Bonferroni-6, signo esperado).")
        log("HORIZONTE: NO IMPORTA — los factores no tienen poder de seleccion intra-dia en")
        log("           ningun horizonte relevante (5d, 10d ni 20d). El desajuste de horizonte")
        log("           era real como problema metodologico, pero no ocultaba ninguna senal:")
        log("           todos los rechazos previos se REFUERZAN.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
