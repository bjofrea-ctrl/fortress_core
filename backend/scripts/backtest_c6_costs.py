"""
PLAN_MEJORA_MATEMATICA §18.1 — Backtest C6 (MA200 fade) con costos reales (2026-08-12).
PRE-REGISTRADO antes de correr (ver §18.1 en el plan).

Pregunta: el fade del IC pooled de C6 (dist_ma200 vs fwd_20d, t=-2.87 en exceso
de mercado) deja retorno NETO positivo despues de costos reales?

Metodologia (pre-registrada):
  - Universo C6 (AAPL, V, MA, ORCL, IBM, QCOM, TXN), 2019-01-01 -> 2026-08-04.
  - Senal identica a §16: dist_ma200 = (close - ema200)/ema200 via
    calculate_all_indicators; fechas de senal con stride 5d POR SIMBOLO.
  - LS (gate): LONG si dist<0, SHORT si dist>0, EW, entrada close[t], salida
    close[t+20] (target exacto de §16). SO (informativa): short-only dist>0.
  - Costos 0.15%/lado x2 = 0.30% por trade unit, deducidos el dia de entrada.
  - Serie diaria del portafolio (promedio EW de trade units activos), Newey-West
    Bartlett L=20.

Criterio (fijado ANTES de correr): LS con n_dias_con_posiciones >= 100 Y media
del retorno diario NETO > 0 con t-NW >= 2.0. SO no participa del gate.
"""
import datetime
import math
import os

import numpy as np
import pandas as pd
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators

C6 = ["AAPL", "V", "MA", "ORCL", "IBM", "QCOM", "TXN"]
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE = 5
COST_ROUND_TRIP = 0.003
NW_LAGS = 20


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """Idéntico a diagnose_gap_reversion.py / backtest_gap_costs.py."""
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
                            f"backtest_c6_costs_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§18.1 — BACKTEST C6 (MA200 fade) CON COSTOS — PRE-REGISTRADO")
    log(f"Universo C6: {', '.join(C6)} | {START} -> {END}")
    log(f"Senal: dist_ma200=(close-ema200)/ema200 | hold {HORIZON}d | stride {STRIDE}d por simbolo")
    log("LS (gate): LONG dist<0 / SHORT dist>0, EW | SO (info): short-only dist>0")
    log(f"Costos: {COST_ROUND_TRIP*100:.2f}%/trade unit (0.15%/lado x2), deducidos al entrar")
    log(f"Criterio: n_dias>=100 Y media NETO diaria > 0 con t-NW>=2.0 (L={NW_LAGS})")
    log("=" * 72)

    price_data = load_universe(C6, START, END)
    log(f"precios cargados: {len(price_data)} simbolos")

    signals = {}
    for sym in C6:
        d = calculate_all_indicators(price_data[sym].sort_index().copy())
        dist = (d["close"] - d["ema200"]) / d["ema200"]
        s = pd.DataFrame({"date": d.index, "dist": dist.to_numpy()}).iloc[::STRIDE]
        s = s.dropna(subset=["dist"])
        signals[sym] = s
        log(f"  {sym}: {len(s)} fechas de senal ({len(s)/len(d)*100:.1f}% del timeline)")

    daily_rets = {sym: price_data[sym].sort_index()["close"].pct_change()
                  for sym in C6}

    units = []
    for sym in C6:
        closes = price_data[sym].sort_index()["close"]
        for _, row in signals[sym].iterrows():
            t = row["date"]
            try:
                i = closes.index.get_loc(t)
            except KeyError:
                continue
            if i + HORIZON >= len(closes):
                continue
            fwd = float(closes.iloc[i + HORIZON] / closes.iloc[i] - 1)
            units.append({"sym": sym, "entry": t, "side": -1 if row["dist"] > 0 else 1,
                          "fwd": fwd, "dist": float(row["dist"])})

    log(f"\ntrade units (LS): {len(units)}")
    if not units:
        log("SIN TRADE UNITS -> sin evaluacion posible")
        log(f"\nOut: {out_path}")
        return

    ls = pd.DataFrame(units)
    so = ls[ls["side"] == -1].copy()

    def port_series(units_df, label):
        """Serie diaria REAL del portafolio: retorno diario del activo por unidad activa.
        La unidad entra al close de `entry` y sale al close de la fila +20 del simbolo
        (exactamente el target de §16, closes.iloc[i+20]/closes.iloc[i] - 1). Los dias
        activos son las 20 filas siguientes del simbolo (i+1 ... i+20): la suma de
        pct_change sobre esos dias reproduce EXACTAMENTE el fwd de la unidad (verificable).
        Costo del trade unit (0.30%) deducido el dia de entrada, prorrateado por el
        numero de unidades activas ese dia."""
        if units_df.empty:
            return None, None
        sym_dates = {sym: daily_rets[sym].index for sym in C6}
        active_sets = []
        for u in units_df.itertuples():
            dates = sym_dates[u.sym]
            i0 = dates.get_loc(u.entry)
            active_sets.append(dates[i0 + 1: i0 + 1 + HORIZON])
        all_days = pd.DatetimeIndex(sorted(
            {u.entry for u in units_df.itertuples()}.union(*[set(a) for a in active_sets])))
        gross = pd.Series(0.0, index=all_days, dtype=float)
        cost = pd.Series(0.0, index=all_days, dtype=float)
        for u in units_df.itertuples():
            dates = sym_dates[u.sym]
            i0 = dates.get_loc(u.entry)
            active = dates[i0 + 1: i0 + 1 + HORIZON]
            if len(active) == 0:
                continue
            sym_rets = daily_rets[u.sym].reindex(active).fillna(0.0)
            contrib = (u.side * sym_rets).to_numpy() / len(active)
            gross.loc[active] += contrib
            cost.loc[u.entry] += COST_ROUND_TRIP / len(active)
        net = gross - cost
        return gross, net

    for label, df in [("LS", ls), ("SO", so)]:
        gross_ser, net_ser = port_series(df, label)
        if gross_ser is None or len(gross_ser) == 0:
            log(f"\n{label}: sin serie diaria (0 unidades)")
            continue
        n_days = len(gross_ser)
        for name, ser in [("BRUTO", gross_ser), ("NETO", net_ser)]:
            z = ser.to_numpy()
            mean = float(z.mean())
            se = newey_west_se(z, NW_LAGS)
            t = mean / se if se > 0 else 0.0
            sharpe = mean / float(z.std(ddof=1)) * math.sqrt(252) if z.std(ddof=1) > 0 else 0.0
            pct_pos = float((z > 0).mean())
            log(f"{label} {name:5s}: media diaria {mean:+.6f} | SE-NW {se:.6f} | t-NW {t:+.2f} "
                f"| Sharpe anualizado {sharpe:+.2f} | % dias positivos {pct_pos*100:.1f}% | n_dias {n_days}")

    gross_ls, net_ls = port_series(ls, "LS")
    n_days_ls = len(net_ls) if net_ls is not None else 0
    if net_ls is not None and n_days_ls > 0:
        mean_net = float(net_ls.mean())
        se_net = newey_west_se(net_ls.to_numpy(), NW_LAGS)
        t_net = mean_net / se_net if se_net > 0 else 0.0
        ok_days = n_days_ls >= 100
        ok_net = mean_net > 0 and t_net >= 2.0
        log("\n--- VEREDICTO (§18.1, pre-registrado, variante LS) ---")
        log(f"n_dias={n_days_ls} (>=100: {ok_days}) | media neta {mean_net:+.6f} t-NW={t_net:+.2f} "
            f"(>0 con t>=2: {ok_net})")
        if ok_days and ok_net:
            log("=> CUMPLE: el fade de MA200 sobrevive costos -> C6 candidato REAL de motor: "
                "diseñar trial de motor pre-registrado (integracion en el motor, slot de n_trials propio).")
        else:
            log("=> NO CUMPLE: el fade de MA200 no sobrevive costos -> §18 se cierra: hallazgo "
                "académico, no traducible a PnL neto. Baseline universo 50 sigue siendo el único "
                "modo de operación documentado.")
    else:
        log("\nLS sin serie diaria -> sin evaluacion posible")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
