"""
PLAN_MEJORA_MATEMATICA §16 — MA200 como soporte/resistencia, ¿heterogéneo por cluster?
(2026-08-12). PRE-REGISTRADO antes de correr.

Motivo: hipótesis del usuario — algunos activos históricamente respetan la media
móvil de 200 como resistencia (mean-reversion: rebote hacia abajo al tocarla desde
abajo), otros la usan como confirmación de tendencia alcista (momentum: superarla
dispara continuación). Un test pooled sobre los 50 símbolos con un solo signo
esperado promediaría estos dos efectos opuestos y podría dar ~0 aunque haya
estructura real en cada subgrupo. Nunca se testeó la heterogeneidad por activo.

Salvaguardas acordadas antes de escribir una línea de análisis:
  1. Clusters ENDÓGENOS ya calculados (§9.b/§9.c, autovectores residuales de RMT,
     sector_clusters_20260811_170235.txt) — NO se inventa una agrupación nueva
     mirando qué separación "funciona mejor".
  2. Bonferroni-8 (8 clusters), umbral |t| > 2.73.
  3. Piso de muestra por cluster: n >= 200 filas (símbolo x fecha) combinadas.

Metodología: señal = distancia a EMA200 = (close - ema200)/ema200 (reusa
calculate_all_indicators, no se reinventa el cálculo). Target = fwd_return_20d,
estride 5d. Por cluster: IC y rank_ic POOLED sobre las fechas x símbolos de ESE
cluster (no cross-sectional día a día — acá la pregunta es si el activo mismo se
comporta distinto según su MA200, no si un símbolo predice mejor que otro el mismo
día; pooled dentro de un grupo de activos similares es la especificación correcta
para esta pregunta, distinta de la de §4.1 que sí exigía intra-día). Newey-West con
n_eff por símbolo (mismo aparato que diagnose_factor_ic.py), sumado dentro del
cluster.

Criterio pre-registrado (sin conocer el resultado): heterogeneidad real si al
menos DOS clusters con n>=200 son significativos (Bonferroni-8) con SIGNOS
OPUESTOS. Si todos los significativos van en la misma dirección, es sólo
diferencia de fuerza, no de comportamiento. Si ninguno es significativo, no hay
evidencia de nada en ningún cluster.
"""
import datetime
import math
import os

import numpy as np
import pandas as pd
from scipy import stats

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators

CLUSTERS = {
    "C0": ["SPY", "QQQ", "NVDA", "TSLA", "AVGO", "BRK-B", "PG", "JNJ", "KO", "PEP", "AMD", "PM"],
    "C1": ["JPM", "BAC", "ADBE", "GE", "INTU", "CAT"],
    "C2": ["CRM", "ACN", "AMGN"],
    "C3": ["WMT", "UNH", "ABBV", "TMO", "MCD", "PFE"],
    "C4": ["META", "LLY", "COST", "MRK", "CSCO"],
    "C5": ["GOOGL", "AMZN", "XOM", "NFLX", "CVX", "LIN", "SPGI"],
    "C6": ["AAPL", "V", "MA", "ORCL", "IBM", "QCOM", "TXN"],
    "C7": ["MSFT", "HD", "CMCSA", "DIS"],
}
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE_DAYS = 5
MIN_N_CLUSTER = 200
N_TESTS = 8
Z_BONFERRONI = float(stats.norm.ppf(1 - (0.05 / N_TESTS) / 2))


def newey_west_neff(records: pd.DataFrame, col: str, fwd_col: str, horizon: int, stride: int) -> float:
    """Idéntico en espíritu a diagnose_factor_ic.py — n_eff por símbolo, sumado."""
    L = int(np.ceil(horizon / stride))
    total = 0.0
    for _, sub in records.groupby("symbol"):
        sub = sub.dropna(subset=[col, fwd_col])
        if len(sub) < 30:
            continue
        x = sub[col].to_numpy()
        y = sub[fwd_col].to_numpy()
        z = (x - x.mean()) * (y - y.mean())
        n = len(z)
        lag_max = min(L, n - 2)
        if lag_max < 1:
            total += n
            continue
        rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
        rho = np.nan_to_num(rho, nan=0.0)
        w = 1 - np.arange(1, len(rho) + 1) / (L + 1)
        denom = 1 + 2 * np.sum(w * rho)
        n_eff_sym = n / max(denom, 1 + L)
        total += n_eff_sym
    return max(total, 30.0)


def build_records(price_data: dict) -> pd.DataFrame:
    rows = []
    for sym, df in price_data.items():
        d = calculate_all_indicators(df.sort_index().copy())
        dist_ma200 = (d["close"] - d["ema200"]) / d["ema200"]
        fwd = d["close"].shift(-HORIZON) / d["close"] - 1
        sub = pd.DataFrame({
            "date": d.index, "symbol": sym,
            "dist_ma200": dist_ma200.to_numpy(), "fwd_return_20d": fwd.to_numpy(),
        })
        rows.append(sub.iloc[::STRIDE_DAYS])
    panel = pd.concat(rows, ignore_index=True)
    return panel.dropna(subset=["dist_ma200", "fwd_return_20d"])


def main():
    out_path = os.path.join("data", "cache",
                            f"diagnose_ma200_clusters_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§16 — MA200 soporte/resistencia por CLUSTER RMT — PRE-REGISTRADO")
    log("Señal: (close-ema200)/ema200 | target: fwd_return_20d | pooled DENTRO de cada cluster")
    log(f"Bonferroni-{N_TESTS} | umbral |t| > {Z_BONFERRONI:.2f} | piso n>={MIN_N_CLUSTER}/cluster")
    log("Clusters: mismos de §9.c (sector_clusters_20260811_170235.txt), no inventados")
    log("=" * 72)

    todos_symbols = sorted({s for members in CLUSTERS.values() for s in members})
    log(f"\nCargando datos... ({len(todos_symbols)} símbolos)")
    price_data = load_universe(todos_symbols, START, END)
    panel = build_records(price_data)
    log(f"Panel: {len(panel)} filas, {panel['symbol'].nunique()} símbolos")

    log(f"\n{'cluster':8s} {'n':>5s} {'mean_IC':>9s} {'rank_IC':>9s} {'t_NW':>7s} {'sig(Bonf)':>10s} {'n>=200':>7s}")
    resultados = {}
    for cname, members in CLUSTERS.items():
        sub = panel[panel["symbol"].isin(members)]
        n = len(sub)
        enough = n >= MIN_N_CLUSTER
        if n < 10:
            log(f"{cname:8s} {n:5d} {'--':>9s} {'--':>9s} {'--':>7s} {'False':>10s} {str(enough):>7s}")
            continue
        ic = float(np.corrcoef(sub["dist_ma200"], sub["fwd_return_20d"])[0, 1])
        rank_ic, _ = stats.spearmanr(sub["dist_ma200"], sub["fwd_return_20d"])
        n_eff = newey_west_neff(sub, "dist_ma200", "fwd_return_20d", HORIZON, STRIDE_DAYS)
        se = 1.0 / math.sqrt(n_eff)
        t = ic / se
        sig = enough and abs(t) > Z_BONFERRONI
        resultados[cname] = {"n": n, "ic": ic, "rank_ic": rank_ic, "t": t, "sig": sig, "enough": enough}
        log(f"{cname:8s} {n:5d} {ic:+9.4f} {rank_ic:+9.4f} {t:+7.2f} {str(sig):>10s} {str(enough):>7s}")

    log("\n--- VEREDICTO (§16, pre-registrado) ---")
    sig_clusters = {k: v for k, v in resultados.items() if v["sig"]}
    if len(sig_clusters) == 0:
        log("=> Ningún cluster significativo (Bonferroni-8). Sin evidencia de MA200 como")
        log("   soporte/resistencia en ningún subgrupo.")
        log("MA200_HETEROGENEIDAD: DESCARTADA (sin señal en ningún cluster)")
    else:
        signos = {k: (v["ic"] > 0) for k, v in sig_clusters.items()}
        positivos = [k for k, pos in signos.items() if pos]
        negativos = [k for k, pos in signos.items() if not pos]
        log(f"=> Clusters significativos: {list(sig_clusters.keys())}")
        log(f"   Signo positivo (momentum, superar MA200 = continuación): {positivos}")
        log(f"   Signo negativo (reversión, MA200 = resistencia real): {negativos}")
        if positivos and negativos:
            log("=> HETEROGENEIDAD REAL: hay clusters con signos opuestos.")
            log("MA200_HETEROGENEIDAD: CONFIRMADA")
        else:
            log("=> Los clusters significativos van todos en la misma dirección —")
            log("   diferencia de FUERZA, no de comportamiento opuesto.")
            log("MA200_HETEROGENEIDAD: NO CONFIRMADA (mismo signo en todos)")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
