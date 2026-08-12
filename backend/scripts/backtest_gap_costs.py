"""
PLAN_MEJORA_MATEMATICA §13.1 — Backtest GAP REVERSION con costos reales (2026-08-12).
PRE-REGISTRADO antes de correr (ver §13.1 en el plan).

Pregunta: tras pagar costos de ejecución (0.15%/lado x 2), ¿el fade intradía del gap
de apertura deja retorno NETO positivo?

Metodología (pre-registrada):
  - Universo 50+7, 2019-01-01 -> 2026-08-04, OHLC real vía load_universe.
  - Días con >= MIN_FADES=3 símbolos con |gap| >= GAP_MIN=1.0%: fade de cada uno
    (short si gap>0, long si gap<0), equally weighted, open -> close del mismo día.
  - Costos: 0.15%/lado x 2 = 0.30% del tamaño por posición completa; aplicado solo
    en días operados -> retorno diario neto = bruto - 0.003.
  - Inferencia: serie de retornos diarios con Newey-West Bartlett L=3.

Criterio de éxito (fijado ANTES de correr):
  - n_dias_operados >= 100 Y media del retorno diario NETO > 0 con t-NW >= 2.0.

El script no decide nada más allá de aplicar este criterio mecánicamente
(regla §3.4: todo número se verifica contra el artefacto).
"""
import datetime
import math
import os

import numpy as np
import pandas as pd
from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
GAP_MIN = 0.01
MIN_FADES = 3
COST_PER_SIDE = 0.0015
NW_LAGS = 3


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """Idéntico a diagnose_gap_reversion.py."""
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


def main():
    out_path = os.path.join("data", "cache",
                            f"backtest_gap_costs_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§13.1 — BACKTEST GAP REVERSION CON COSTOS — PRE-REGISTRADO")
    log(f"Universo: {len(SYMBOLS)} símbolos | {START} -> {END}")
    log(f"Estrategia: fade intradía open->close de símbolos con |gap|>=1.0% "
        f"(>= {MIN_FADES}/día), EW | costos {COST_PER_SIDE*100:.2f}%/lado x 2")
    log(f"Criterio: n_dias>=100 Y media retorno NETO diario > 0 con t-NW>=2.0 (L={NW_LAGS})")
    log("=" * 72)

    price_data = load_universe(SYMBOLS, START, END)
    log(f"precios cargados: {len(price_data)} símbolos")

    rows = []
    for sym, df in price_data.items():
        d = df.sort_index().copy()
        if not {"open", "close"}.issubset(d.columns):
            continue
        close_prev = d["close"].shift(1)
        gap = (d["open"] - close_prev) / close_prev
        fwd = (d["close"] - d["open"]) / d["open"]
        sub = pd.DataFrame({"date": d.index, "symbol": sym, "gap": gap.to_numpy(), "fwd": fwd.to_numpy()})
        rows.append(sub)
    panel = pd.concat(rows, ignore_index=True).dropna(subset=["gap", "fwd"])

    dates = sorted(panel["date"].unique())
    daily = []
    for date in dates:
        day = panel[panel["date"] == date]
        day = day[abs(day["gap"]) >= GAP_MIN]
        n = len(day)
        if n < MIN_FADES:
            continue
        rets = -np.sign(day["gap"].to_numpy()) * day["fwd"].to_numpy()
        gross = float(rets.mean())
        daily.append({"date": date, "n_fades": n, "gross": gross,
                      "net": gross - 2 * COST_PER_SIDE})
    daily_df = pd.DataFrame(daily)
    n_days = len(daily_df)

    log(f"Panel: {len(panel)} filas | días con >= {MIN_FADES} fades: {n_days} "
        f"({n_days / len(dates) * 100:.1f}% de {len(dates)} días de trading)")
    if n_days == 0:
        log("NO HAY DÍAS OPERABLES -> sin evaluación posible")
        log(f"\nOut: {out_path}")
        return

    mean_fades = float(daily_df["n_fades"].mean())
    log(f"fades/día: media {mean_fades:.1f} (min {daily_df['n_fades'].min()}, "
        f"max {daily_df['n_fades'].max()})")

    for col in ["gross", "net"]:
        z = daily_df[col].to_numpy()
        mean = float(z.mean())
        se = newey_west_se(z, NW_LAGS)
        t = mean / se if se > 0 else 0.0
        sharpe = mean / float(z.std(ddof=1)) * math.sqrt(252) if z.std(ddof=1) > 0 else 0.0
        pct_pos = float((z > 0).mean())
        log(f"\n{col.upper():5s}: media diaria {mean:+.5f} | SE-NW {se:.5f} | "
            f"t-NW {t:+.2f} | Sharpe anualizado {sharpe:+.2f} | % días positivos {pct_pos*100:.1f}%")

    mean_net = float(daily_df["net"].mean())
    se_net = newey_west_se(daily_df["net"].to_numpy(), NW_LAGS)
    t_net = mean_net / se_net if se_net > 0 else 0.0
    ok_days = n_days >= 100
    ok_net = mean_net > 0 and t_net >= 2.0

    log("\n--- VEREDICTO (§13.1, pre-registrado) ---")
    log(f"n_dias={n_days} (>=100: {ok_days}) | media neta {mean_net:+.5f} t-NW={t_net:+.2f} "
        f"(>0 con t>=2: {ok_net})")
    if ok_days and ok_net:
        log("=> CUMPLE: el fade sobrevive costos (0.30%/trade) -> justificado evaluar "
            "motor intradía de verdad (con pre-registro propio).")
    else:
        log("=> NO CUMPLE: el fade no sobrevive costos -> §13 se cierra: hallazgo "
            "académico, no traducible a PnL neto con esta infraestructura.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
