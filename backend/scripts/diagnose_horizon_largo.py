"""
PLAN_MEJORA_MATEMATICA §21.1 (M1b) — HORIZONTES LARGOS (2026-08-13).
PRE-REGISTRADO antes de correr.

Motivo: §21 (M1) varió el horizonte sólo hacia el lado CORTO (5d, 10d) respecto del
20d histórico, motivado por la tenencia real del motor (mediana 11d). Pero quedó sin
testear el lado LARGO, y hay una razón académica fuerte para hacerlo: el factor
principal del motor es `momentum_12_1` (construcción clásica de Jegadeesh-Titman
1993), y la evidencia académica del momentum vive en tenencias de 3 a 12 MESES, no
de 20 días hábiles (~1 mes). Es decir: se estuvo midiendo el poder predictivo del
momentum en un horizonte más corto que aquel donde su evidencia original existe.

Pregunta: los factores tienen poder de selección intra-día a 60d (~3 meses) y 125d
(~6 meses), horizontes donde la literatura clásica de momentum SÍ documenta efecto?

Metodología: idéntica a §21/§0.5a (rank IC intra-día, Spearman por fecha, promedio
con SE Newey-West). Lags NW escalados: L = ceil(H/5) -> 12 para 60d, 25 para 125d.

  LIMITACIÓN DECLARADA ANTES DE CORRER: con L=25 y ~187 fechas útiles, los lags son
  ~13% de la muestra — el estimador Newey-West pierde precisión cuando los lags son
  una fracción grande del n. Por eso NO se testea 250d (L=50, ~27% de n, no
  confiable). 125d es el límite razonable con esta muestra, y su t debe leerse con
  esa reserva.

  CHECK DE FIDELIDAD (igual que §21): el fwd_20 recalculado debe reproducir la
  columna fwd_return_20d del panel; si no, se aborta sin interpretar.

Criterio pre-registrado (sin conocer el resultado):
  - Hipótesis nuevas: 3 factores x 2 horizontes largos (60d, 125d) = 6 tests.
  - CORRECCIÓN CONSERVADORA: en vez de Bonferroni-6 sobre esta familia sola, se usa
    Bonferroni-12 sobre la familia COMPLETA de auditoría de horizonte (3 factores x
    4 horizontes no-históricos: 5d, 10d, 60d, 125d — incluyendo los 6 tests ya
    corridos en §21). Umbral |t| > 2.87. Se elige el umbral MÁS ESTRICTO a
    propósito: la pregunta "¿el horizonte oculta señal?" es una sola familia de
    hipótesis, y corregir por todos los horizontes probados es la lectura honesta.
    (No se re-interpreta §21 con este umbral — §21 ya cerró con su criterio propio;
    esto sólo fija la vara para los tests nuevos, en la dirección más exigente.)
  - Signo esperado: positivo (mayor score -> mayor retorno).
  - VEREDICTO: si algún factor es significativo a 60d o 125d con signo esperado, el
    horizonte largo importa y hay que revisar las refutaciones en ese horizonte. Si
    ninguno lo es, la auditoría de horizonte se cierra COMPLETA: no hay señal en
    ningún horizonte entre 1 semana y 6 meses.

El script NO decide nada por sí mismo más que aplicar este criterio mecánicamente.
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
HORIZONS_NUEVOS = [60, 125]
HORIZONTE_REFERENCIA = 20
STRIDE_DAYS = 5
MIN_SYMBOLS = 5
N_TESTS_FAMILIA_COMPLETA = 12  # 3 factores x 4 horizontes (5,10,60,125)
Z_BONFERRONI = float(stats.norm.ppf(1 - (0.05 / N_TESTS_FAMILIA_COMPLETA) / 2))
TOL_FIDELIDAD = 1e-6


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
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
                            f"horizon_largo_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 80)
    log("§21.1 (M1b) — HORIZONTES LARGOS: rank IC intra-dia a 60d/125d — PRE-REGISTRADO")
    log("Motivo: momentum_12_1 es Jegadeesh-Titman clasico, cuya evidencia vive en tenencias")
    log("        de 3-12 MESES; se estuvo midiendo a 20d habiles (~1 mes), mas corto que eso.")
    log(f"Bonferroni-{N_TESTS_FAMILIA_COMPLETA} sobre la familia COMPLETA de horizonte "
        f"(5/10/60/125d) | umbral |t| > {Z_BONFERRONI:.2f}")
    log("LIMITACION declarada: 250d NO se testea (L=50 = ~27% de la muestra, NW no confiable).")
    log("                      125d (L=25, ~13%) es el limite razonable; leer su t con reserva.")
    log("=" * 80)

    path = latest_panel()
    panel = pd.read_parquet(path)
    panel["date"] = pd.to_datetime(panel["date"])
    elig = panel[panel["eligible"]].copy()
    log(f"\nPanel: {os.path.basename(path)} | filas eligible: {len(elig)}")

    log(f"Cargando precios ({len(SYMBOLS)} simbolos)...")
    price_data = load_universe(SYMBOLS, START, END)
    fwd = build_forwards(price_data, HORIZONS_NUEVOS + [HORIZONTE_REFERENCIA])
    fwd["date"] = pd.to_datetime(fwd["date"])
    merged = elig.merge(fwd, on=["date", "symbol"], how="left")

    comp = merged[merged["fwd_return_20d"].notna() & merged["fwd_20"].notna()]
    max_diff = float((comp["fwd_return_20d"] - comp["fwd_20"]).abs().max()) if len(comp) else float("nan")
    fidelidad_ok = len(comp) > 0 and max_diff < TOL_FIDELIDAD
    log(f"\n--- CHECK DE FIDELIDAD (§14) ---")
    log(f"fwd_20 recalculado vs panel: n={len(comp)} | max |dif| = {max_diff:.3e}")
    log(f"FIDELIDAD: {'OK -> se evalua' if fidelidad_ok else 'FALLA -> NO se interpreta'}")
    if not fidelidad_ok:
        log("\nAbortado por fidelidad.")
        log(f"\nOut: {out_path}")
        return

    log(f"\n{'factor':16s} {'horiz':>7s} {'tipo':>10s} {'n_days':>7s} {'mean_IC':>9s} "
        f"{'SE_NW':>8s} {'t':>7s} {'L_NW':>5s} {'sig(Bonf12)':>12s}")
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
            log(f"{factor:16s} {h:6d}d {tipo:>10s} {res['n_days']:7d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {lags:5d} {marca:>12s}")

    log(f"\n--- VEREDICTO (§21.1, pre-registrado) ---")
    if hallazgos:
        log(f"=> {len(hallazgos)} hallazgo(s) significativo(s) a horizonte largo:")
        for factor, h, res in hallazgos:
            log(f"   {factor} a {h}d: IC {res['mean_ic']:+.4f}, t-NW {res['t']:+.2f}")
        log("HORIZONTE LARGO: IMPORTA — hay poder de seleccion que los tests a 5-20d no")
        log("                 capturaban. Revisar refutaciones en el horizonte correcto.")
    else:
        log("=> Ningun factor es significativo a 60d ni a 125d (Bonferroni-12, signo esperado).")
        log("HORIZONTE: AUDITORIA COMPLETA Y CERRADA — sin senal de seleccion en NINGUN")
        log("           horizonte entre 1 semana y 6 meses (5d, 10d, 20d, 60d, 125d).")
        log("           El horizonte no era el problema; no hay senal que el horizonte ocultara.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
