"""
PLAN_MEJORA_MATEMATICA §11.1 — RE-EVALUACIÓN del trial (a) basket ADX con métrica
apropiada para timing de UN activo (2026-08-11). PRE-REGISTRADO ANTES de correr.

Motivo: el veredicto DSR 0/3 del trial #14 usó el criterio congelado (DSR>=0.90,
piso 30 trades) diseñado para el motor de 50 símbolos. Para un gate LONG/FLAT de
UN solo activo, n=10-12 trades/ventana es estructural (51 trades en 2915 días) y
el DSR colapsa a ~0 por incertidumbre de estimación, no por falta de edge. La
muestra correcta es la SERIE DIARIA de retornos de la estrategia.

Metodología fijada en §11.1 (no se cambia después de correr):
  1. Serie: replica EXACTA del trial #14 — basket equal-weight 50 (rebalanceo
     diario, MIN_BASKET_MEMBERS=40), ADX(14) de Wilder sobre el cierre del basket
     (high=low=close), regla LONG si ADX>25 / FLAT si ADX<20 / 20-25 mantiene
     (histéresis), costos 0.15%/lado en transiciones, 2019-01-01 -> 2026-08-04.
  2. VERIFICACIÓN DE FIDELIDAD antes de evaluar: ADX mediana ~= 28.1 y ~51 trades
     vs artefacto trial14_basket_adx_20260811_215113.txt. Si no coinciden,
     la serie NO es la del trial y NO se evalúa.
  3. Por ventana W1/W2/W3 sobre retornos diarios: media diaria, Sharpe anualizado
     (x sqrt(252)), Sortino anualizado (downside std), t de Newey-West sobre la
     media (H0: mu=0, HAC, L = floor(4*(n/100)^(2/9)), kernel Bartlett).
  4. Contexto: delta diario estrategia - buy&hold del basket por ventana con su
     t-NW (informa si el timing agrega valor sobre MANTENER el basket).
  5. Criterio pre-registrado: (a) sobrevive si t-NW(media diaria) > 2 en >= 2/3
     ventanas. El veredicto DSR 0/3 original NO se borra; queda documentado como
     mal especificado para 1 activo.

El script NO decide nada por sí mismo: escribe el artefacto con huella timestamp
y la interpretación la hace el §11.1 del plan. Ver regla §3.4.
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
MIN_BASKET_MEMBERS = 40
INITIAL_CAPITAL = 25000.0
COST_PER_SIDE = 0.001 + 0.0005  # 0.15%/lado, igual baseline y trial
LONG_ABOVE = 25.0
FLAT_BELOW = 20.0
WINDOWS = [
    ("W1 2020-2021", "2020-01-01", "2021-12-31"),
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]
TRIAL_ARTIFACT_ADX_MED = 28.1
TRIAL_ARTIFACT_TRADES = 51


def build_basket_series(price_data: dict) -> pd.DataFrame:
    """Serie del basket equal-weight (rebalanceo diario), MISMA construcción
    que el trial #14 y la re-medición de régimen."""
    closes = {s: d["close"] for s, d in price_data.items() if "close" in d and len(d) > 200}
    frame = pd.DataFrame(closes).sort_index()
    rets = frame.pct_change()
    member_count = rets.notna().sum(axis=1)
    rets = rets.where(member_count >= MIN_BASKET_MEMBERS)
    basket_ret = rets.mean(axis=1).dropna()
    basket = (1 + basket_ret).cumprod()
    basket = basket / basket.iloc[0] * INITIAL_CAPITAL
    return pd.DataFrame({"basket": basket, "basket_ret": basket_ret})


def adx_series(close: pd.Series) -> pd.Series:
    """ADX(14) de Wilder sobre el cierre del basket (high=low=close), MISMO
    código del trial #14."""
    high = low = close
    plus_dm = high.diff().clip(lower=0)
    minus_dm = -low.diff().clip(upper=0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1
    ).max(axis=1)
    atr_ = tr.rolling(window=14).mean()
    plus_di = 100 * plus_dm.rolling(window=14).mean() / atr_
    minus_di = 100 * minus_dm.rolling(window=14).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(window=14).mean()


def simulate_long_flat(adx: pd.Series, basket_ret: pd.Series) -> pd.DataFrame:
    """Simulación LONG/FLAT con histéresis (20-25 mantiene) y costos 0.15%/lado
    en transiciones. Devuelve retorno diario neto de la estrategia y la posición."""
    pos = np.zeros(len(adx))
    for i in range(len(adx)):
        a = adx.iloc[i]
        if pd.isna(a):
            pos[i] = 0.0  # sin señal -> flat (motor)
        elif a > LONG_ABOVE:
            pos[i] = 1.0
        elif a < FLAT_BELOW:
            pos[i] = 0.0
        else:
            pos[i] = pos[i - 1] if i > 0 else 0.0  # 20-25 mantiene
    pos_prev = pd.Series(pos).shift(1).fillna(0.0).to_numpy()
    gross = pos_prev * basket_ret.to_numpy()
    transition = np.abs(np.diff(np.concatenate([[0.0], pos])))
    costs = transition * COST_PER_SIDE
    net = gross - costs
    return pd.DataFrame({"pos": pos, "gross": gross, "costs": costs, "net": net},
                        index=adx.index)


def newey_west_t(x: np.ndarray) -> float:
    """t de Newey-West sobre la media de x (H0: mu=0), HAC kernel Bartlett,
    L = floor(4*(n/100)^(2/9))."""
    n = len(x)
    if n < 30:
        return float("nan")
    mu = x.mean()
    demean = x - mu
    L = int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))
    L = max(1, min(L, n - 2))
    gamma0 = np.mean(demean ** 2)
    se2 = gamma0
    for k in range(1, L + 1):
        w = 1.0 - k / (L + 1)
        gam = np.mean(demean[:-k] * demean[k:])
        se2 += 2.0 * w * gam
    if se2 <= 0:
        return float("nan")
    se = math.sqrt(se2 / n)
    return mu / se


def sharpe(x: np.ndarray, ann: float = 252.0) -> float:
    if len(x) < 2 or np.std(x) == 0:
        return float("nan")
    return float(np.mean(x) / np.std(x, ddof=1) * math.sqrt(ann))


def sortino(x: np.ndarray, ann: float = 252.0) -> float:
    downside = x[x < 0]
    if len(x) < 2 or len(downside) == 0:
        return float("nan")
    dd = np.sqrt(np.mean(downside ** 2))
    if dd == 0:
        return float("nan")
    return float(np.mean(x) / dd * math.sqrt(ann))


def main():
    out_path = os.path.join("data", "cache",
                            f"reeval_trial14_basket_adx_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§11.1 RE-EVALUACIÓN trial (a) — métrica apropiada para timing de UN activo (PRE-REGISTRADO)")
    log(f"Universo basket: {len(SYMBOLS)} símbolos (equal-weight, rebalanceo diario)")
    log("Regla: LONG si ADX>25 / FLAT si ADX<20 / 20-25 mantiene | costos 0.0015/lado")
    log("Método: serie DIARIA de retornos; t-NW sobre media (L=floor(4(n/100)^(2/9)), Bartlett)")
    log("Criterio: t-NW(media) > 2 en >= 2/3 ventanas -> (a) sobrevive")
    log("=" * 72)

    # --- Datos y serie (replica exacta del trial #14) ---
    log("\nCargando datos...")
    price_data = load_universe(SYMBOLS, START, END)
    basket_df = build_basket_series(price_data)
    adx = adx_series(basket_df["basket"])
    sim = simulate_long_flat(adx, basket_df["basket_ret"])
    log(f"Basket: {len(basket_df)} días | {basket_df.index[0]:%Y-%m-%d} -> {basket_df.index[-1]:%Y-%m-%d}")

    # --- VERIFICACIÓN DE FIDELIDAD vs artefacto del trial ---
    n_trades = int(np.sum(np.diff(sim["pos"].to_numpy()) > 0.5))
    adx_med = float(adx.median())
    log(f"\n--- VERIFICACIÓN DE FIDELIDAD vs trial14_basket_adx_20260811_215113.txt ---")
    log(f"ADX mediana: {adx_med:.1f} (trial: {TRIAL_ARTIFACT_ADX_MED}) | "
        f"trades (flat->long): {n_trades} (trial: {TRIAL_ARTIFACT_TRADES})")
    fid_ok = (abs(adx_med - TRIAL_ARTIFACT_ADX_MED) < 0.5 and
              abs(n_trades - TRIAL_ARTIFACT_TRADES) <= 2)
    log(f"FIDELIDAD: {'OK -> se evalúa' if fid_ok else 'FALLA -> NO se evalúa'}")
    if not fid_ok:
        log("\nOut (abortado por fidelidad): " + out_path)
        return

    # --- Métricas por ventana sobre la serie diaria ---
    log(f"\n    {'ventana':13s} {'n_dias':>6s} {'media_d':>8s} {'sharpe':>7s} {'sortino':>7s} "
        f"{'t_NW':>6s} {'sig>2':>5s} {'delta_vs_H':>9s} {'t_NW_delta':>10s}")
    sig_windows = 0
    for name, s, e in WINDOWS:
        mask = (adx.index >= pd.Timestamp(s)) & (adx.index <= pd.Timestamp(e))
        net = sim["net"].loc[mask].to_numpy()
        bh = basket_df["basket_ret"].loc[mask].to_numpy()
        delta = net - bh
        t_nw = newey_west_t(net)
        t_delta = newey_west_t(delta)
        sig = not math.isnan(t_nw) and t_nw > 2.0
        if sig:
            sig_windows += 1
        sh = sharpe(net)
        so = sortino(net)
        log(f"    {name:13s} {len(net):6d} {np.mean(net):+8.5f} {sh:7.3f} {so:7.3f} "
            f"{t_nw:+6.2f} {str(sig):>5s} {np.mean(delta):+9.5f} {t_delta:+10.2f}")

    # --- Veredicto pre-registrado ---
    log("\n--- VEREDICTO (§11.1, pre-registrado) ---")
    log(f"Ventanas con t-NW(media diaria) > 2: {sig_windows}/3")
    if sig_windows >= 2:
        log("=> (a) SOBREVIVE: el timing ADX del basket tiene media diaria "
            "significativamente positiva en >=2/3 ventanas.")
    else:
        log("=> (a) DESCARTADA por el estadístico correcto: la media diaria del "
            "timing ADX del basket NO es significativamente > 0 en >=2/3 ventanas.")
    log("\nContexto (NO es el criterio): t-NW(delta estrategia - buy&hold) informa "
        "si el timing agrega valor sobre MANTENER el basket.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
