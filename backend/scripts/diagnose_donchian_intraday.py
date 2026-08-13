"""
PLAN_MEJORA_MATEMATICA §17 — Canal de Donchian, rank IC intra-día (2026-08-12).
PRE-REGISTRADO antes de correr.

Motivo: hipótesis del usuario — cerca de máximos/mínimos recientes se acumulan
stop-loss y márgenes de otros traders; romper esos niveles puede disparar
cascadas (liquidaciones/stops) que generan movimientos abruptos, funcionando
como soporte/resistencia o gatillo de continuación. No podemos ver el libro de
órdenes real (información privada de cada broker) — el proxy público más cercano
y ya implementado en este proyecto es el Canal de Donchian (máximo/mínimo de 20
días, "sistema Turtle"), citado en RESEARCH_PREDICTIVE_INDICATORS.md (Donchian
1970; Shumway & Wu 2006) con un IC esperado de 0.05-0.08 — pero NUNCA se le
corrió el mismo test riguroso que al resto de los factores.

Metodología (mismo protocolo exacto que diagnose_rr2_intraday.py — rank IC
intra-día, Newey-West, NO pooled): se reusa el panel limpio ya construido
(factor_panel_20260811_144857.parquet, con fwd_return_20d y eligible ya
calculados correctamente) y se le agrega una 5ta columna: donchian_score =
(close - donchian_mid) / (donchian_upper - donchian_lower) — posición continua
dentro del canal (positivo = cerca/sobre el máximo, negativo = cerca/bajo el
mínimo), calculado con donchian_channel() ya existente en predictive_indicators.py
(no se reinventa el cálculo). Signo esperado +1 (breakout alcista = continuación),
igual que el resto de los factores direccionales del proyecto.

Criterio pre-registrado (sin conocer el resultado): |t| > 2.0, mismo umbral que
diagnose_rr2_intraday.py original (un solo factor nuevo, no hay corrección de
múltiples comparaciones porque no se testean otros factores en este script).

El script NO decide nada por sí mismo más que aplicar este criterio mecánicamente.
"""
import datetime
import glob
import os

import numpy as np
import pandas as pd
from scipy import stats

from app.core.data_ingestion import load_universe
from app.core.predictive_indicators import donchian_channel
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE_DAYS = 5
MIN_SYMBOLS = 5
L = int(np.ceil(HORIZON / STRIDE_DAYS))


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
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


def build_donchian_scores(price_data: dict) -> pd.DataFrame:
    rows = []
    for sym, df in price_data.items():
        d = df.sort_index().copy()
        upper, mid, lower = donchian_channel(d, period=20)
        width = (upper - lower).replace(0, np.nan)
        score = (d["close"] - mid) / width
        rows.append(pd.DataFrame({"date": d.index, "symbol": sym, "donchian_score": score.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def intraday_rank_ic(panel: pd.DataFrame) -> dict:
    daily_ics = []
    dates = panel["date"].unique()
    for date in dates:
        day = panel[panel["date"] == date]
        day = day[day["donchian_score"].notna() & day["fwd_return_20d"].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day["donchian_score"], day["fwd_return_20d"])
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
                            f"diagnose_donchian_intraday_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§17 — Canal de Donchian, rank IC intra-día — PRE-REGISTRADO")
    log("Señal: (close - donchian_mid) / (donchian_upper - donchian_lower), 20d")
    log("Mismo protocolo que diagnose_rr2_intraday.py | signo esperado: +1 | umbral |t|>2.0")
    log("=" * 72)

    path = latest_panel()
    panel = pd.read_parquet(path)
    panel["date"] = pd.to_datetime(panel["date"])
    log(f"\nCargando precios para calcular Donchian ({len(SYMBOLS)} símbolos)...")
    price_data = load_universe(SYMBOLS, START, END)
    donch = build_donchian_scores(price_data)
    donch["date"] = pd.to_datetime(donch["date"])

    merged = panel[panel["eligible"] & panel["fwd_return_20d"].notna()].merge(
        donch, on=["date", "symbol"], how="left"
    )
    log(f"Panel: {os.path.basename(path)} | filas eligible con Donchian: "
        f"{merged['donchian_score'].notna().sum()} de {len(merged)}")

    res = intraday_rank_ic(merged)
    sig = (not np.isnan(res["t"])) and res["t"] > 2.0

    log(f"\n{'factor':16s} {'n_days':>7s} {'mean_IC':>9s} {'SE_NW':>8s} {'t':>7s} {'veredicto':>18s}")
    v = "SIGNIFICATIVO" if sig else "no sig"
    log(f"{'donchian_score':16s} {res['n_days']:7d} {res['mean_ic']:+9.4f} "
        f"{res['se_nw']:8.4f} {res['t']:+7.2f} {v:>18s}")

    log("\n--- VEREDICTO (§17, pre-registrado) ---")
    if sig:
        log("=> Donchian muestra rank IC intra-día significativo con el signo esperado.")
        log("DONCHIAN: SIGNIFICATIVO — candidato a re-testear con Bonferroni si se combina con otros factores")
    else:
        log("=> Donchian NO muestra rank IC intra-día significativo. Mismo destino que")
        log("   momentum/RSI/trend/ADX en §0.5a: implementado y documentado, sin poder de")
        log("   selección real medido con el mismo rigor.")
        log("DONCHIAN: DESCARTADO")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
