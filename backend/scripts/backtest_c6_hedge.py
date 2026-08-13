"""
PLAN_MEJORA_MATEMATICA §18.2 — Backtest C6 HEDGEADO (market-neutral por beta) con
costos — INTENTO FINAL de la linea C6 (2026-08-13). PRE-REGISTRADO antes de correr.

Pregunta: §18.1 fallo porque la pata short paga el drift completo del mercado
(E[sign*fwd]=+0.00017, P(dist>0) >> 0.5). El hallazgo de §18 predice retorno
RELATIVO al mercado (t=-2.87 en exceso). Una version del fade neutralizada por
beta de mercado con costos reales, deja NETO diario > 0 con t-NW >= 2.0?

Metodologia (pre-registrada):
  - Mismas unidades, señal, ventana y mecanica que §18.1 (dist_ma200, stride 5d,
    hold 20d, entry al close, salida t+20, costos 0.15%/lado por pata). Panel debe
    reproducir n=3703, Pearson IC -0.1582, Spearman -0.1129 (check de integridad).
  - Pata hedge: cada unit SHORT (dist>0) se cubre comprando |beta_sym| de SPY;
    decision de diseno declarada ANTES de correr: la pata LONG se cubre simetricamente
    shorteando beta_sym de SPY (cubrir solo el short dejaria drift residual).
  - Beta: OLS diario (ret_sym ~ ret_SPY, con constante) sobre la ventana PRE-MUESTRA
    2015-01-01 -> 2018-12-31; NADA de la ventana de test participa del estimador.
  - Costos: 0.003 * (1+|beta|) por trade unit hedged (C6 round-trip + SPY round-trip
    proporcional al beta), deducidos el dia de entrada, misma convencion §18.1.

Criterio (fijado ANTES de correr, identico a §18.1): n_dias >= 100 Y media del
retorno diario NETO > 0 con t-NW >= 2.0 (L=20). SO-hedged informativa, NO gate.

Regla de parada (compromiso del usuario, 2026-08-13): este es el INTENTO FINAL de
C6. NO CUMPLE -> §18 se cierra DEFINITIVO, sin tercera variante: C6 = hallazgo
academico en exceso de mercado. CUMPLE -> C6 candidato REAL de motor (trial
pre-registrado con slot de n_trials propio).
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
BETA_START = "2015-01-01"
BETA_END = "2018-12-31"
HORIZON = 20
STRIDE = 5
COST_SIDE = 0.0015
NW_LAGS = 20


def newey_west_se(z: np.ndarray, lags: int) -> float:
    """Idéntico a §18.1 (backtest_c6_costs.py)."""
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


def estimate_betas(log):
    """Beta pre-muestra 2015-2018: OLS diario ret_sym ~ ret_SPY con constante."""
    data = load_universe(C6 + ["SPY"], BETA_START, BETA_END)
    spy = data["SPY"].sort_index()["close"].pct_change()
    betas = {}
    for sym in C6:
        r = data[sym].sort_index()["close"].pct_change()
        x = spy.reindex(r.index).fillna(0.0).to_numpy()
        y = r.fillna(0.0).to_numpy()
        A = np.column_stack([x, np.ones(len(x))])
        coef = np.linalg.lstsq(A, y, rcond=None)[0]
        betas[sym] = float(coef[0])
        log(f"  beta pre-muestra {sym}: {coef[0]:+.3f}")
    return betas


def main():
    out_path = os.path.join("data", "cache",
                            f"backtest_c6_hedge_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§18.2 — BACKTEST C6 HEDGEADO (market-neutral por beta) CON COSTOS — PRE-REGISTRADO")
    log(f"Universo C6: {', '.join(C6)} | {START} -> {END} | beta pre-muestra {BETA_START} -> {BETA_END}")
    log(f"Senal: dist_ma200=(close-ema200)/ema200 | hold {HORIZON}d | stride {STRIDE}d por simbolo")
    log("HEDGE (gate): fade LS + pata opuesta en SPY de tamano |beta_sym| (ambas patas)")
    log(f"Costos: {COST_SIDE*100:.2f}%/lado x 2 patas = 0.003*(1+|beta|) por unit, al entrar")
    log(f"Criterio: n_dias>=100 Y media NETO diaria > 0 con t-NW>=2.0 (L={NW_LAGS})")
    log("REGLA DE PARADA (usuario): intento FINAL de C6; NO CUMPLE -> §18 cerrado DEFINITIVO")
    log("=" * 72)

    betas = estimate_betas(log)
    mean_abs_beta = float(np.mean([abs(b) for b in betas.values()]))
    log(f"  |beta| medio: {mean_abs_beta:.3f}")

    price_data = load_universe(C6, START, END)
    log(f"precios cargados (ventana de test): {len(price_data)} simbolos")

    signals = {}
    for sym in C6:
        d = calculate_all_indicators(price_data[sym].sort_index().copy())
        dist = (d["close"] - d["ema200"]) / d["ema200"]
        s = pd.DataFrame({"date": d.index, "dist": dist.to_numpy()}).iloc[::STRIDE]
        s = s.dropna(subset=["dist"])
        signals[sym] = s

    daily_rets = {sym: price_data[sym].sort_index()["close"].pct_change()
                  for sym in C6}
    spy_data = load_universe(["SPY"], START, END)
    spy_rets = spy_data["SPY"].sort_index()["close"].pct_change()

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

    panel_dists = ls["dist"].to_numpy()
    panel_fwds = ls["fwd"].to_numpy()
    pearson = float(np.corrcoef(panel_dists, panel_fwds)[0, 1])
    rho_s = float(pd.Series(panel_dists).corr(pd.Series(panel_fwds), method="spearman"))
    p_pos = float((panel_dists > 0).mean())
    e_sign_fwd = float(np.sign(panel_dists).dot(panel_fwds) / len(panel_dists))
    log(f"\nCHECK DE INTEGRIDAD (§14): n={len(ls)} | Pearson IC {pearson:+.4f} "
        f"(§16: -0.1582) | Spearman {rho_s:+.4f} (§16: -0.1129) | P(dist>0) {p_pos:.3f} | "
        f"E[sign*fwd] {e_sign_fwd:+.6f}")

    def port_series(units_df, label):
        """Serie diaria del portafolio HEDGEADO: la unidad aporta side*r_sym/HORIZON
        mas la pata de mercado -side*beta*r_spy/HORIZON (opuesta en SPY). Los dias
        activos son las 20 filas del simbolo (i+1 .. i+20), igual que §18.1.
        Costo 0.003*(1+|beta|) deducido el dia de entrada, prorrateado por el
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
            mkt_rets = spy_rets.reindex(active).fillna(0.0)
            contrib = (u.side * sym_rets - u.side * betas[u.sym] * mkt_rets).to_numpy() / len(active)
            gross.loc[active] += contrib
            cost.loc[u.entry] += (COST_SIDE * 2 * (1 + abs(betas[u.sym]))) / len(active)
        net = gross - cost
        return gross, net

    for label, df in [("LS-HEDGE", ls), ("SO-HEDGE", so)]:
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

    gross_ls, net_ls = port_series(ls, "LS-HEDGE")
    n_days_ls = len(net_ls) if net_ls is not None else 0
    if net_ls is not None and n_days_ls > 0:
        mean_net = float(net_ls.mean())
        se_net = newey_west_se(net_ls.to_numpy(), NW_LAGS)
        t_net = mean_net / se_net if se_net > 0 else 0.0
        ok_days = n_days_ls >= 100
        ok_net = mean_net > 0 and t_net >= 2.0
        log("\n--- VEREDICTO (§18.2, pre-registrado, variante LS-HEDGE) ---")
        log(f"n_dias={n_days_ls} (>=100: {ok_days}) | media neta {mean_net:+.6f} t-NW={t_net:+.2f} "
            f"(>0 con t>=2: {ok_net})")
        if ok_days and ok_net:
            log("=> CUMPLE: el fade hedgeado sobrevive costos -> C6 candidato REAL de motor: "
                "diseñar trial de motor pre-registrado (integracion en el motor, slot de n_trials propio).")
        else:
            log("=> NO CUMPLE (INTENTO FINAL): §18 se cierra DEFINITIVO — C6 queda como hallazgo "
                "académico en exceso de mercado, sin tercera variante. Baseline universo 50 sigue "
                "siendo el único modo de operación documentado. Siguiente frente: Fase 1 EVT o "
                "Fase 2 Kalman+GP-BO (decisión del usuario).")
    else:
        log("\nLS-HEDGE sin serie diaria -> sin evaluacion posible")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
