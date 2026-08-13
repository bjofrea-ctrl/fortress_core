"""
PLAN_MEJORA_MATEMATICA §19 — Diagnóstico EVT de colas del universo 50 (2026-08-13).
PRE-REGISTRADO antes de correr (ver §19 en el plan).

Pregunta: los retornos diarios de los activos del universo 50 (2019-2026) tienen
colas de PERDIDA mas pesadas que la normal estandar que la regla ATR del motor
asume de facto (stop 2xATR, adaptive_risk.py)?

Metodologia (pre-registrada):
  - Universo 50 = 7 originales + NEW_UNIVERSE (43), 2019-01-01 -> 2026-08-04.
  - Estandarizacion EWMA (lambda=0.94, RiskMetrics; arch/GARCH no instalado en
    el venv - limitacion declarada): sigma_t^2 = 0.94*sigma_{t-1}^2 + 0.06*r_{t-1}^2,
    arranque = varianza muestral de los primeros 60 retornos; z_t = r_t/sigma_t.
  - GPD MLE (scipy genpareto, loc=0) sobre excesos de perdida: L = -z, umbral u =
    percentil 95% empirico (~5% excesos).
  - Por activo: xi con SE ~ (1+xi)/sqrt(N_u), VaR_GPD(99%), ES_GPD(99%) en z,
    cuantil empirico 99%, VaR normal 2.326, ratio. Cola derecha informativa.
  - Backtest de cola: % de dias con r_t < -2.326*sigma_t (esperado 1% si normal)
    y con r_t < -VaR_GPD*sigma_t (esperado ~1% si calibra). Ljung-Box(10) sobre z^2.

Gate del diagnostico (fijado ANTES de correr): PASA si AMBAS:
  1. >=30% de los activos (>=15/50) con xi > 0 significativo (t > 1.64 unilateral); Y
  2. >=30% de los activos con excesos empiricos bajo el VaR normal >= 1.5%.
Si NO pasa: colas compatibles con normalidad -> no se justifica el trial de stops
EVT -> Fase 1 se cierra con este diagnostico como evidencia.
"""
import datetime
import os

import numpy as np
import pandas as pd
from app.core.data_ingestion import load_universe
from scipy import stats
from scipy.stats import genpareto
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)
START = "2019-01-01"
END = "2026-08-04"
LAMBDA = 0.94
WARMUP = 60
U_QUANTILE = 0.95
VAR_LEVEL = 0.99
LB_LAGS = 10


def ewma_vol(r: pd.Series) -> pd.Series:
    r2 = r.to_numpy()
    var0 = float(np.var(r2[:WARMUP], ddof=1))
    var = [var0] * WARMUP
    v = var0
    for t in range(WARMUP, len(r2)):
        v = LAMBDA * v + (1 - LAMBDA) * r2[t - 1] ** 2
        var.append(v)
    return pd.Series(np.sqrt(var), index=r.index)


def fit_gpd_left(excesses: np.ndarray):
    """GPD por MLE sobre excesos positivos de perdida (genpareto, loc=0)."""
    shape, _, scale = genpareto.fit(excesses, floc=0)
    n = len(excesses)
    se = (1 + shape) / np.sqrt(n) if shape > -0.5 else float("nan")
    return shape, scale, se


def var_es_gpd(shape, scale, u, n_excs, n_obs, level=VAR_LEVEL):
    """VaR/ES de la cola de perdida (unidades de z), formulas McNeil."""
    if abs(shape) < 1e-12:
        var = u + scale * np.log(n_obs / n_excs * (1 - level))
    else:
        var = u + scale / shape * ((n_obs / n_excs * (1 - level)) ** (-shape) - 1)
    es = (var + scale - shape * u) / (1 - shape) if shape < 1 else float("nan")
    return var, es


def ljung_box(z2: np.ndarray, lags: int) -> float:
    n = len(z2)
    if n <= lags:
        return 0.0
    z2 = z2 - z2.mean()
    acf = np.array([np.corrcoef(z2[:-j], z2[j:])[0, 1] if j < n else 0.0
                    for j in range(1, lags + 1)])
    acf = np.nan_to_num(acf, nan=0.0)
    q = n * (n + 2) * np.sum(acf ** 2 / np.arange(n - 1, n - lags - 1, -1))
    return float(1 - stats.chi2.cdf(q, lags))


def main():
    out_path = os.path.join("data", "cache",
                            f"evt_tails_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§19 — DIAGNOSTICO EVT DE COLAS (universo 50) — PRE-REGISTRADO")
    log(f"Universo: {len(SYMBOLS)} simbolos | {START} -> {END}")
    log(f"Estandarizacion: EWMA vol lambda={LAMBDA}, arranque {WARMUP}d | umbral POT p{U_QUANTILE:.0%}")
    log("Limitacion declarada: arch/GARCH NO instalado -> EWMA (McNeil-Frey simplificado)")
    log("Gate (fijado ANTES): (1) >=15/50 activos con xi>0 sig (t>1.64) Y (2) >=30% "
        "activos con excesos bajo VaR-normal >= 1.5%")
    log("=" * 72)

    price_data = load_universe(SYMBOLS, START, END)
    log(f"precios cargados: {len(price_data)}/{len(SYMBOLS)}")

    rows = []
    for sym in SYMBOLS:
        close = price_data[sym].sort_index()["close"]
        r = close.pct_change().dropna()
        if len(r) < 500:
            log(f"  {sym}: serie corta ({len(r)}) -> SKIP")
            continue
        sig = ewma_vol(r)
        z = (r / sig).to_numpy()
        z = z[np.isfinite(z)]
        L = -z
        u = float(np.quantile(L, U_QUANTILE))
        exc = L[L > u] - u
        if len(exc) < 30:
            log(f"  {sym}: solo {len(exc)} excesos -> SKIP")
            continue
        xi, beta, se_xi = fit_gpd_left(exc)
        var_gpd, es_gpd = var_es_gpd(xi, beta, u, len(exc), len(z))
        var_emp = float(np.quantile(L, VAR_LEVEL))
        var_norm = float(-stats.norm.ppf(1 - VAR_LEVEL))  # +2.326 en unidades de perdida L=-z
        excess_norm = float((L > var_norm).mean())
        excess_gpd = float((L > var_gpd).mean())
        lb = ljung_box(z ** 2, LB_LAGS)
        # cola derecha informativa
        exc_r = z[z > u] - u
        xi_r = genpareto.fit(exc_r, floc=0)[0] if len(exc_r) >= 30 else float("nan")
        rows.append({
            "sym": sym, "n": len(z), "excs": len(exc), "xi": xi, "se": se_xi,
            "t": xi / se_xi if se_xi and se_xi > 0 else 0.0,
            "var_gpd": var_gpd, "es_gpd": es_gpd, "var_emp": var_emp, "var_norm": var_norm,
            "ratio": var_gpd / var_norm, "excess_norm": excess_norm, "excess_gpd": excess_gpd,
            "lb": lb, "xi_r": xi_r,
        })

    df = pd.DataFrame(rows).set_index("sym")
    n_syms = len(df)
    n_sig = int((df["t"] > 1.64).sum())
    n_exc = int((df["excess_norm"] >= 0.015).sum())

    log(f"\n{'sym':6s} {'n':5s} {'exc':4s} {'xi':6s} {'t':5s} {'VaR99GPD':>9s} {'VaR99emp':>9s} {'VaR99N':>7s} "
        f"{'ratio':>5s} {'excN%':>6s} {'excG%':>6s} {'LB':>5s}")
    for sym, row in df.iterrows():
        log(f"{sym:6s} {int(row['n']):5d} {int(row['excs']):4d} {row['xi']:+.3f} {row['t']:+.2f} "
            f"{row['var_gpd']:9.3f} {row['var_emp']:9.3f} {row['var_norm']:7.3f} "
            f"{row['ratio']:5.2f} {row['excess_norm']*100:6.2f} {row['excess_gpd']*100:6.2f} {row['lb']:5.2f}")

    log("\n--- AGREGADO ---")
    log(f"activos evaluados: {n_syms}/50 | xi>0 significativo (t>1.64): {n_sig} "
        f"({n_sig/n_syms*100:.0f}%) | excesos bajo VaR-normal >=1.5%: {n_exc} "
        f"({n_exc/n_syms*100:.0f}%)")
    log(f"xi medio: {df['xi'].mean():+.3f} | mediana: {df['xi'].median():+.3f} | "
        f"p25/p75: {df['xi'].quantile(.25):+.3f}/{df['xi'].quantile(.75):+.3f}")
    log(f"ratio VaR_GPD/VaR_normal: media {df['ratio'].mean():.2f} | mediana {df['ratio'].median():.2f} "
        f"| max {df['ratio'].max():.2f}")
    log(f"excesos VaR-normal: media {df['excess_norm'].mean()*100:.2f}% | "
        f"mediana {df['excess_norm'].median()*100:.2f}%")
    log(f"excesos VaR-GPD: media {df['excess_gpd'].mean()*100:.2f}% (esperado ~1%)")
    log(f"Ljung-Box(10) z2 significativo (<0.05): {(df['lb']<0.05).sum()}/{n_syms} activos "
        f"(vol residual no capturada por EWMA)")

    gate1 = n_sig >= 15
    gate2 = n_exc >= 0.30 * n_syms
    log("\n--- VEREDICTO (§19, pre-registrado) ---")
    log(f"gate1: xi>0 sig en {n_sig} activos (>=15: {gate1}) | "
        f"gate2: excesos>=1.5% en {n_exc} activos (>=30%: {gate2})")
    if gate1 and gate2:
        log("=> PASA: colas mas pesadas que normal, de forma material y generalizada -> "
            "se pre-registra el trial de stops EVT del motor.")
    else:
        log("=> NO PASA: colas compatibles con normalidad (o no generalizadas) -> la regla "
            "ATR no esta sistematicamente subdimensionada -> NO se justifica el trial de "
            "stops EVT; Fase 1 se cierra con este diagnostico como evidencia.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
