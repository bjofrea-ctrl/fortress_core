"""
PLAN_MEJORA_MATEMATICA §22 — LEAD-LAG ENTRE SIMBOLOS (Tarea C, PLAN_LARGO_PLAZO.md).
PRE-REGISTRADO antes de correr (ver §22 en el plan).

Pregunta: el retorno de un simbolo "lider" predice el retorno de un simbolo
"seguidor" del mismo sector/cadena a horizontes de 1-5 dias?

Metodologia (pre-registrada):
  - Universo 50 (7 originales + NEW_UNIVERSE), 2019-01-01 -> 2026-08-04.
  - Retornos diarios r_sym[t] = close[t]/close[t-1] - 1 por simbolo.
  - Para cada par (lider L, seguidor F) y cada lag k en {1,2,3,4,5}:
    correlacion cruzada de Spearman entre r_L[t-k] y r_F[t] sobre fechas comunes,
    con SE Newey-West (mismo aparato que §0.5a/§21, lags NW = k).
  - Signo esperado: POSITIVO (el lider anticipa al seguidor en la misma direccion).

Criterio pre-registrado (fijado ANTES de correr, sin conocer el resultado):
  - Tests: 10 pares x 5 lags = 50 tests.
  - Bonferroni-50 sobre los tests nuevos -> umbral |t| > ~3.48 (z 0.05/50 bilateral).
  - Un par es un hallazgo si >=2 lags CONSECUTIVOS del mismo par cruzan el umbral
    con signo esperado positivo (evita que un lag aislado sea ruido).
  - VEREDICTO: si algun par cumple -> lead-lag real, candidato a pre-registro de
    motor (familia motor_signal). Si ninguno -> hipotesis refutada con la vara mas
    estricta usada en el proyecto.

Riesgo declarado: pares elegidos por cadena/sector ANTES de ver resultados (cero
grados de libertad post-hoc); lags fijos en 1-5 dias sin mirar datos. Si sale un
par significativo, se valida contra sub-periodo PRE/POST 2022 antes de concluir.

El script NO decide nada por si mismo mas que aplicar este criterio mecanicamente.
"""
import datetime
import os

import numpy as np
from scipy import stats

from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)
START = "2019-01-01"
END = "2026-08-04"
LAGS = [1, 2, 3, 4, 5]

# Lista de pares (lider, seguidor) fijada en el pre-registro §22 ANTES de correr.
PARES = [
    ("NVDA", "AMD"),
    ("NVDA", "AVGO"),
    ("NVDA", "QCOM"),
    ("AAPL", "MSFT"),
    ("AAPL", "GOOGL"),
    ("MSFT", "GOOGL"),
    ("XOM", "CVX"),
    ("JPM", "BAC"),
    ("AMZN", "WMT"),
    ("LLY", "JNJ"),
]

N_TESTS = len(PARES) * len(LAGS)  # 50
Z_BONFERRONI = float(stats.norm.ppf(1 - (0.05 / N_TESTS) / 2))
MIN_LAGS_CONSECUTIVOS = 2


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """SE con correccion Newey-West (mismo aparato que §0.5a/§21)."""
    n = len(z)
    if n < 3:
        return float(np.std(z, ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    lag_max = min(lags, n - 2)
    if lag_max < 1:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (lags + 1)
    denom = 1 + 2 * np.sum(w * rho)
    n_eff = n / max(denom, 1.0)
    return float(np.std(z, ddof=1) / np.sqrt(n_eff))


def main():
    out_path = os.path.join("data", "cache",
                            f"lead_lag_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 80)
    log("§22 (Tarea C) — LEAD-LAG ENTRE SIMBOLOS: correlacion cruzada desfasada")
    log(f"Pares: {len(PARES)} | Lags: {LAGS} | Tests: {N_TESTS}")
    log(f"Bonferroni-{N_TESTS} -> umbral |t| > {Z_BONFERRONI:.2f}")
    log("Criterio: >=2 lags consecutivos con |t|>umbral y signo esperado POSITIVO")
    log("=" * 80)

    log(f"\nCargando precios ({len(SYMBOLS)} simbolos, {START} -> {END})...")
    price_data = load_universe(SYMBOLS, START, END)
    rets = {}
    for sym, df in price_data.items():
        close = df.sort_index()["close"]
        r = close.pct_change()
        rets[sym] = r
        log(f"  {sym}: {len(r.dropna())} retornos")

    log("\n--- RESULTADOS (Spearman lider[t-k] vs seguidor[t]) ---")
    log(f"{'par':14s} {'lag':>3s} {'n_dias':>7s} {'mean_rho':>9s} {'se_nw':>8s} {'t':>7s}  veredicto")

    hallazgos = []
    resultados = {}
    for lider, seguidor in PARES:
        rl = rets.get(lider)
        rf = rets.get(seguidor)
        if rl is None or rf is None:
            log(f"\n[aviso] par {lider}->{seguidor}: falta simbolo en el universo — se omite")
            continue
        # Alinear por fecha comun
        common = rl.index.intersection(rf.index)
        rl_c, rf_c = rl.loc[common], rf.loc[common]
        par_sig = []
        for k in LAGS:
            # r_L[t-k] vs r_F[t]: desfasar el lider hacia atras
            x = rl_c.shift(k).dropna()
            y = rf_c.loc[x.index]
            mask = x.notna() & y.notna()
            x, y = x[mask], y[mask]
            if len(x) < 30:
                par_sig.append(False)
                log(f"{lider}->{seguidor:8s} {k:3d} {len(x):7d} {'':>9s} {'':>8s} {'':>7s}  n<30")
                continue
            rho, _ = stats.spearmanr(x, y)
            se = newey_west_se(np.asarray(y.values), k)
            t = rho / se if se > 0 else 0.0
            sig = abs(t) > Z_BONFERRONI
            signo_ok = t > 0  # signo esperado: positivo
            veredicto = ""
            if sig and signo_ok:
                veredicto = "SIG(+)"
            elif sig:
                veredicto = "SIG(-)"
            par_sig.append(sig and signo_ok)
            resultados[(lider, seguidor, k)] = {"rho": rho, "se": se, "t": t, "sig": sig}
            log(f"{lider}->{seguidor:8s} {k:3d} {len(x):7d} {rho:9.4f} {se:8.4f} {t:7.2f}  {veredicto}")

        # Criterio: >=2 lags consecutivos significativos con signo positivo
        consec = 0
        max_consec = 0
        for s in par_sig:
            consec = consec + 1 if s else 0
            max_consec = max(max_consec, consec)
        if max_consec >= MIN_LAGS_CONSECUTIVOS:
            hallazgos.append((lider, seguidor, max_consec))

    log("\n--- VEREDICTO (§22, pre-registrado) ---")
    if hallazgos:
        log(f"Hallazgo: {len(hallazgos)} pares con >=2 lags consecutivos SIG(+)")
        for lider, seguidor, n_consec in hallazgos:
            log(f"  {lider} -> {seguidor}: {n_consec} lags consecutivos")
        log("=> Se valida contra sub-periodo PRE/POST 2022 antes de concluir (regla §22).")
    else:
        log("Ningun par con >=2 lags consecutivos SIG(+) -> hipotesis de lead-lag")
        log("refutada con Bonferroni-50 (la vara mas estricta usada en el proyecto).")
        log("=> NO CUMPLE el criterio de hallazgo.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
