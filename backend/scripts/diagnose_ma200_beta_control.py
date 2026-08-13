"""
PLAN_MEJORA_MATEMATICA §18 — Control de beta de mercado sobre el hallazgo MA200 C3/C6
(2026-08-12). PRE-REGISTRADO antes de correr.

Motivo: §16 encontró que C3 (WMT/UNH/ABBV/TMO/MCD/PFE, t=-3.26) y C6
(AAPL/V/MA/ORCL/IBM/QCOM/TXN, t=-4.31) muestran IC negativo real (Bonferroni-8)
entre distancia sobre MA200 y retorno forward 20d. Reserva explícita dejada en
§16: el test es pooled dentro de cluster, vulnerable a que el efecto sea sólo
beta de mercado (rallies generales preceden correcciones) en vez de algo
idiosincrático del activo.

Metodología: mismo panel y misma señal que §16 (dist_ma200), pero el TARGET
cambia de retorno crudo a retorno EN EXCESO DEL MERCADO: excess_fwd_return_20d =
fwd_return_20d(activo) - fwd_return_20d(SPY), misma ventana, mismas fechas. Si el
efecto sobrevive usando exceso sobre el mercado, es evidencia de que no es sólo
beta. Mismos clusters C3/C6 (los únicos que fueron significativos en §16 — no se
re-testean los otros 6, evita inflar falsamente la potencia post-hoc filtrando a
los "ganadores" sin decirlo: se reportan igual para que quede documentado, pero
el criterio de decisión es sólo sobre C3 y C6).

Criterio pre-registrado (sin conocer el resultado): Bonferroni-2 (sólo C3 y C6 se
evalúan contra el criterio, los otros 6 son contexto), umbral |t| > 2.24
(two-sided, alpha familiar 0.05/2). Si C3 y/o C6 siguen significativos con el
mismo signo usando retorno EN EXCESO del mercado, el hallazgo se sostiene como
idiosincrático. Si pierden significancia, era beta.
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
CLUSTERS_A_DECIDIR = ["C3", "C6"]
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE_DAYS = 5
MIN_N_CLUSTER = 200
Z_BONFERRONI = float(stats.norm.ppf(1 - (0.05 / len(CLUSTERS_A_DECIDIR)) / 2))


def newey_west_neff(records: pd.DataFrame, col: str, fwd_col: str, horizon: int, stride: int) -> float:
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


def build_records(price_data: dict, spy_fwd: pd.Series) -> pd.DataFrame:
    rows = []
    for sym, df in price_data.items():
        d = calculate_all_indicators(df.sort_index().copy())
        dist_ma200 = (d["close"] - d["ema200"]) / d["ema200"]
        fwd = d["close"].shift(-HORIZON) / d["close"] - 1
        sub = pd.DataFrame({
            "date": d.index, "symbol": sym,
            "dist_ma200": dist_ma200.to_numpy(), "fwd_return_20d": fwd.to_numpy(),
        })
        sub = sub.set_index("date")
        sub["spy_fwd"] = spy_fwd
        sub["excess_fwd_return_20d"] = sub["fwd_return_20d"] - sub["spy_fwd"]
        rows.append(sub.reset_index().iloc[::STRIDE_DAYS])
    panel = pd.concat(rows, ignore_index=True)
    return panel.dropna(subset=["dist_ma200", "fwd_return_20d", "excess_fwd_return_20d"])


def test_cluster(sub: pd.DataFrame, target: str) -> dict:
    n = len(sub)
    ic = float(np.corrcoef(sub["dist_ma200"], sub[target])[0, 1])
    n_eff = newey_west_neff(sub, "dist_ma200", target, HORIZON, STRIDE_DAYS)
    se = 1.0 / math.sqrt(n_eff)
    t = ic / se
    return {"n": n, "ic": ic, "t": t}


def main():
    out_path = os.path.join("data", "cache",
                            f"diagnose_ma200_beta_control_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§18 — Control de BETA DE MERCADO sobre hallazgo MA200 C3/C6 — PRE-REGISTRADO")
    log("Target: retorno EN EXCESO de SPY (fwd_return_20d(activo) - fwd_return_20d(SPY))")
    log(f"Bonferroni-2 (sólo C3/C6 deciden) | umbral |t| > {Z_BONFERRONI:.2f}")
    log("=" * 72)

    todos_symbols = sorted({s for members in CLUSTERS.values() for s in members} | {"SPY"})
    log(f"\nCargando datos... ({len(todos_symbols)} símbolos)")
    price_data = load_universe(todos_symbols, START, END)
    spy_close = price_data["SPY"]["close"].sort_index()
    spy_fwd = spy_close.shift(-HORIZON) / spy_close - 1

    panel = build_records(price_data, spy_fwd)
    log(f"Panel: {len(panel)} filas")

    log(f"\n{'cluster':8s} {'n':>5s} {'IC crudo':>9s} {'t crudo':>8s} "
        f"{'IC exceso':>10s} {'t exceso':>9s} {'decide':>7s} {'sobrevive':>10s}")
    for cname, members in CLUSTERS.items():
        sub = panel[panel["symbol"].isin(members)]
        crudo = test_cluster(sub, "fwd_return_20d")
        exceso = test_cluster(sub, "excess_fwd_return_20d")
        decide = cname in CLUSTERS_A_DECIDIR
        sobrevive = decide and abs(exceso["t"]) > Z_BONFERRONI and np.sign(exceso["ic"]) == np.sign(crudo["ic"])
        log(f"{cname:8s} {crudo['n']:5d} {crudo['ic']:+9.4f} {crudo['t']:+8.2f} "
            f"{exceso['ic']:+10.4f} {exceso['t']:+9.2f} {str(decide):>7s} "
            f"{(str(sobrevive) if decide else '—'):>10s}")

    log("\n--- VEREDICTO (§18, pre-registrado, sólo C3/C6 deciden) ---")
    resultados = {}
    for cname in CLUSTERS_A_DECIDIR:
        sub = panel[panel["symbol"].isin(CLUSTERS[cname])]
        crudo = test_cluster(sub, "fwd_return_20d")
        exceso = test_cluster(sub, "excess_fwd_return_20d")
        sobrevive = abs(exceso["t"]) > Z_BONFERRONI and np.sign(exceso["ic"]) == np.sign(crudo["ic"])
        resultados[cname] = sobrevive
        estado = "SOBREVIVE (idiosincrático, no sólo beta)" if sobrevive else "NO SOBREVIVE (era beta de mercado)"
        log(f"  {cname}: t crudo={crudo['t']:+.2f} -> t exceso-mercado={exceso['t']:+.2f} => {estado}")

    if any(resultados.values()):
        log("\n=> Al menos un cluster sostiene el efecto controlando por mercado: hay algo")
        log("   idiosincrático real, no sólo beta. MA200_C3C6: VALIDADO (parcial o total)")
    else:
        log("\n=> Ningún cluster sostiene el efecto controlando por mercado: el hallazgo de §16")
        log("   era beta de mercado disfrazada, no un efecto específico del activo.")
        log("MA200_C3C6: REFUTADO (era beta de mercado)")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
