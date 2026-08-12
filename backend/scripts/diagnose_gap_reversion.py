"""
PLAN_MEJORA_MATEMATICA §13 — Diagnóstico GAP REVERSION intra-día (2026-08-12).
PRE-REGISTRADO antes de correr.

Contexto: surge de un informe de Cline que citaba "overnight gap reversion" como
el signal #1 del Medallion Fund (19.4% feature importance), atribuido al repo
`gurmansaran/medallion-pub`. Verificado: ese repo es la réplica de un desconocido
(0 estrellas, 1 solo push, backtest propio con 12x de apalancamiento etiquetado
"12x Medallion") — NO son datos reales de Renaissance Technologies, que jamás
publicó sus señales. Se descarta esa cita como autoridad. La idea de gap-fade
en sí es legítima y tiene sustento académico independiente (literatura de
retornos overnight vs intraday) — se testea acá con el mismo rigor de siempre,
sin ninguna presunción de que "funciona porque lo dice Medallion".

Hipótesis: el gap overnight (open[t] vs close[t-1]) predice reversión de corto
plazo — gap grande hacia arriba -> retorno subsiguiente negativo (fade), y
viceversa. Es un fenómeno de corto plazo por diseño (la literatura lo ubica
intradía a pocos días), NO se testea a 20d como momentum/RSI — eso diluiría
cualquier efecto real.

Metodología (mismo aparato que diagnose_rr2_intraday.py — rank IC intra-día,
Newey-West sobre la serie de ICs diarios, NO pooled):
  - Señal: gap_pct[t] = (open[t] - close[t-1]) / close[t-1], universo 50+7 símbolos.
  - 3 targets, horizontes cortos (fade se espera y decae rápido):
      fwd_intraday_0d = (close[t] - open[t]) / open[t]   (mismo día — el test
                         clásico de "gap fade": ¿el precio vuelve durante el día?)
      fwd_close_1d    = (close[t+1] - close[t]) / close[t]
      fwd_close_5d    = (close[t+5] - close[t]) / close[t]
  - Por cada fecha: Spearman(gap, target) entre símbolos disponibles ese día
    (rank IC intra-día, no pooled — mismo error que se corrigió en §4.1).
    Promedio de ICs diarios con SE Newey-West (Bartlett, L=horizonte en días,
    mínimo 1), sobre TODAS las fechas de trading (stride=1, no 5 — horizontes
    cortos no necesitan sub-muestrear).
  - Signo esperado: NEGATIVO (reversión) en los 3 horizontes.

Criterio pre-registrado (sin conocer el resultado): gap reversion tiene
evidencia real si al menos un horizonte da |t-NW| > 2 CON el signo negativo
esperado. Si no, se descarta como el resto de las variables refutadas de
`RESUMEN_VALIDACION_VARIABLES.md`.

El script NO decide nada por sí mismo más que aplicar este criterio
mecánicamente. Ver regla §3.4: todo número se verifica contra el artefacto.
"""
import datetime
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
MIN_SYMBOLS = 5
HORIZONS = {"fwd_intraday_0d": 1, "fwd_close_1d": 1, "fwd_close_5d": 5}  # L de NW


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """Idéntico a diagnose_rr2_intraday.py."""
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


def build_gap_panel(price_data: dict) -> pd.DataFrame:
    """Panel largo (date, symbol, gap_pct, 3 targets) desde OHLC crudo."""
    rows = []
    for sym, df in price_data.items():
        d = df.sort_index().copy()
        if not {"open", "close"}.issubset(d.columns):
            continue
        close_prev = d["close"].shift(1)
        gap_pct = (d["open"] - close_prev) / close_prev
        fwd_intraday_0d = (d["close"] - d["open"]) / d["open"]
        fwd_close_1d = d["close"].shift(-1) / d["close"] - 1
        fwd_close_5d = d["close"].shift(-5) / d["close"] - 1
        sub = pd.DataFrame({
            "date": d.index, "symbol": sym, "gap_pct": gap_pct.to_numpy(),
            "fwd_intraday_0d": fwd_intraday_0d.to_numpy(),
            "fwd_close_1d": fwd_close_1d.to_numpy(),
            "fwd_close_5d": fwd_close_5d.to_numpy(),
        })
        rows.append(sub)
    panel = pd.concat(rows, ignore_index=True)
    return panel.dropna(subset=["gap_pct"])


def intraday_rank_ic(panel: pd.DataFrame, target: str, L: int) -> dict:
    daily_ics = []
    dates = panel["date"].unique()
    for date in dates:
        day = panel[panel["date"] == date]
        day = day[day["gap_pct"].notna() & day[target].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day["gap_pct"], day[target])
        if np.isfinite(rho):
            daily_ics.append(rho)
    ics = np.array(daily_ics)
    n_days = len(ics)
    if n_days == 0:
        return {"n_days": 0, "mean_ic": float("nan"), "se_nw": float("nan"), "t": float("nan")}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, L)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(n_days), "mean_ic": mean_ic, "se_nw": se_nw, "t": t}


def main():
    out_path = os.path.join("data", "cache",
                            f"diagnose_gap_reversion_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§13 — DIAGNÓSTICO GAP REVERSION intra-día — PRE-REGISTRADO")
    log("Señal: gap_pct = (open[t]-close[t-1])/close[t-1] | rank IC intra-día, Newey-West")
    log("Horizontes: mismo día (open->close), +1d close, +5d close | signo esperado: NEGATIVO")
    log("Criterio: algún horizonte con |t-NW|>2 Y signo negativo -> evidencia real")
    log("=" * 72)

    log("\nCargando datos...")
    price_data = load_universe(SYMBOLS, START, END)
    panel = build_gap_panel(price_data)
    log(f"Panel gap: {len(panel)} filas, {panel['symbol'].nunique()} símbolos, "
        f"{panel['date'].nunique()} fechas")

    log(f"\n{'target':18s} {'n_days':>7s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'veredicto':>18s}")
    any_hit = False
    for target, L in HORIZONS.items():
        res = intraday_rank_ic(panel, target, L)
        sig_neg = (not math.isnan(res["t"])) and res["t"] < -2.0
        if sig_neg:
            any_hit = True
        v = "REVERSIÓN REAL" if sig_neg else ("sig. signo contrario" if abs(res["t"]) > 2.0 and not math.isnan(res["t"]) else "no sig")
        log(f"{target:18s} {res['n_days']:7d} {res['mean_ic']:+9.4f} {res['se_nw']:8.4f} "
            f"{res['t']:+7.2f} {v:>18s}")

    log("\n--- VEREDICTO (§13, pre-registrado) ---")
    if any_hit:
        log("=> Al menos un horizonte muestra reversión intra-día real (|t-NW|>2, signo negativo).")
        log("GAP_REVERSION: EVIDENCIA REAL")
    else:
        log("=> Ningún horizonte muestra reversión significativa con el signo esperado.")
        log("GAP_REVERSION: DESCARTADO (mismo patrón que el resto de RESUMEN_VALIDACION_VARIABLES)")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
