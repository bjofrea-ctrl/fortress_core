"""
PLAN_MEJORA_MATEMATICA §12 — Diagnóstico régimen vs VOLATILIDAD realizada (2026-08-12).
PRE-REGISTRADO antes de correr.

Contexto: el condicionamiento régimen+macro se testeó DOS veces como predictor de
RETORNO futuro (Fase 2 original, panel con lookahead §3.1; y §11.1 sobre la serie
del basket con régimen limpio) y las dos veces se refutó. Pero eso sólo prueba que
régimen no predice DIRECCIÓN — nunca se testeó si predice MAGNITUD (volatilidad
realizada), que es una pregunta distinta y con mucho más sustento académico (la
literatura de regime-switching para vol-targeting/risk-parity no depende de acertar
signo, sólo magnitud). Motivación de producto: TARGET_VOLATILITY existe en
config.py sin conectar (RESUMEN_VALIDACION_VARIABLES §5).

Metodología (fijada aquí, no implícita):
  - Misma serie que trial #14/§11.1: basket equal-weight de 50 símbolos
    (rebalanceo diario, MIN_BASKET_MEMBERS=40).
  - Mismo régimen que §11.1: HMM walk-forward, fit <= 2024-12-31, decodificación
    Viterbi expansiva sin fechas futuras (label_regimes_walk_forward, idéntico a
    remeasure_regime_basket.py).
  - Target: volatilidad realizada FORWARD 20d del basket = std(retornos diarios
    del basket en (t, t+20]) * sqrt(252), en fechas estrided cada 5d (mismo
    stride que el resto de los diagnósticos de este plan).
  - Por régimen (n >= 200 para contar): media de vol realizada, y t de Newey-West
    de (vol_en_regimen - vol_media_global) contra 0 (HAC Bartlett,
    L=floor(4*(n/100)^(2/9)), mismo aparato que §11.1/newey_west_t).

Criterio pre-registrado (sin conocer el resultado):
  Régimen tiene valor de RIESGO si al menos un régimen con n>=200 difiere de la
  vol media global con |t-NW| > 2. Si ningún régimen con muestra suficiente
  difiere, régimen NO aporta señal de riesgo tampoco (además de no predecir
  retorno) y queda descartado como input de vol-targeting.

El script NO decide nada por sí mismo más que aplicar este criterio mecánicamente;
la interpretación de producto la hace el plan. Ver regla §3.4: todo número se
verifica contra el artefacto.
"""
import datetime
import math
import os

import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.regime_classifier import GlobalRegimeClassifier
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX",
                 "DX-Y.NYB", "GC=F", "SI=F", "CL=F", "HG=F"]
FIT_END = "2024-12-31"
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE_DAYS = 5
MIN_BASKET_MEMBERS = 40
MIN_SAMPLE_PER_REGIME = 200


def build_basket_series(price_data: dict) -> pd.DataFrame:
    """Idéntico a trial #14 / §11.1 / remeasure_regime_basket.py."""
    closes = {s: d["close"] for s, d in price_data.items() if "close" in d and len(d) > 200}
    frame = pd.DataFrame(closes).sort_index()
    rets = frame.pct_change()
    member_count = rets.notna().sum(axis=1)
    rets = rets.where(member_count >= MIN_BASKET_MEMBERS)
    basket_ret = rets.mean(axis=1).dropna()
    basket = (1 + basket_ret).cumprod()
    return pd.DataFrame({"basket": basket, "basket_ret": basket_ret})


def label_regimes_walk_forward(clf: GlobalRegimeClassifier, price_data: dict) -> pd.Series:
    """Idéntico a remeasure_regime_basket.py — Viterbi sobre [inicio, t], sin fechas futuras."""
    feats = clf._extract_features(price_data)
    dates = feats.index
    states = np.full(len(feats), -1, dtype=int)
    scaled_all = clf.scaler.transform(feats.values)
    for i in range(len(feats)):
        if i < 60:
            continue
        chunk = scaled_all[: i + 1]
        try:
            raw = clf.model.predict(chunk)
        except Exception:
            continue
        aligned = clf._align_states(raw, feats.iloc[: i + 1])
        states[i] = int(aligned[-1])
    return pd.Series(states, index=dates)


def newey_west_t(x: np.ndarray) -> float:
    """Idéntico a reeval_trial14_basket_adx.py — t-NW sobre la media de x (H0: mu=0)."""
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


def main():
    out_path = os.path.join("data", "cache",
                            f"diagnose_regime_vol_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§12 — DIAGNÓSTICO régimen vs VOLATILIDAD REALIZADA (no retorno) — PRE-REGISTRADO")
    log(f"Basket equal-weight {len(SYMBOLS)} símbolos | horizonte {HORIZON}d fwd | stride {STRIDE_DAYS}d")
    log(f"Régimen HMM walk-forward (fit<={FIT_END}) | piso n>=200 por régimen")
    log("Criterio: algún régimen con n>=200 difiere de la vol media global con |t-NW|>2")
    log("=" * 72)

    log("\nCargando datos...")
    market_data = load_universe(MACRO_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)

    basket_df = build_basket_series(price_data)
    log(f"\nBasket construido: {len(basket_df)} días, {START} -> {basket_df.index[-1]:%Y-%m-%d}")

    fit_data = {t: df[df.index <= pd.Timestamp(FIT_END)] for t, df in market_data.items()}
    clf = GlobalRegimeClassifier(n_states=4)
    clf.fit(fit_data)
    log(f"HMM fiteado con datos <= {FIT_END}")
    reg_series = label_regimes_walk_forward(clf, market_data)
    reg_series = reg_series.reindex(basket_df.index)

    # --- Volatilidad realizada forward 20d, estrided 5d ---
    rets = basket_df["basket_ret"].to_numpy()
    dates = basket_df.index
    n = len(dates)
    rec = []
    for i in range(0, n - HORIZON, STRIDE_DAYS):
        date = dates[i]
        regime = int(reg_series.loc[date]) if reg_series.loc[date] >= 0 else -1
        if regime < 0:
            continue
        fwd_window = rets[i + 1: i + 1 + HORIZON]
        if len(fwd_window) < HORIZON or np.isnan(fwd_window).any():
            continue
        vol_fwd = float(np.std(fwd_window, ddof=1) * math.sqrt(252))
        rec.append({"date": date, "regime": regime, "vol_fwd": vol_fwd})
    rec = pd.DataFrame(rec)
    log(f"\nRegistros régimen-vs-volatilidad: {len(rec)} (estrided {STRIDE_DAYS}d, h={HORIZON}d)")

    global_mean_vol = rec["vol_fwd"].mean()
    log(f"Volatilidad realizada media global (todas las fechas): {global_mean_vol:.4f}")

    # --- Vol realizada por régimen ---
    log(f"\n    {'régimen':12s} {'n':>5s} {'vol_media':>10s} {'vol_std':>8s} "
        f"{'delta_vs_global':>15s} {'t_NW':>6s} {'sig>2':>5s} {'enough(n>=200)':>15s}")
    verdicts = []
    for r in range(4):
        sub = rec[rec["regime"] == r]
        n_r = len(sub)
        if n_r == 0:
            log(f"    {clf.state_labels[r]:12s} {'0':>5s}")
            continue
        vol_mean = sub["vol_fwd"].mean()
        vol_std = sub["vol_fwd"].std()
        delta = sub["vol_fwd"].to_numpy() - global_mean_vol
        t_nw = newey_west_t(delta)
        sig = not math.isnan(t_nw) and abs(t_nw) > 2.0
        enough = n_r >= MIN_SAMPLE_PER_REGIME
        verdicts.append({"r": r, "name": clf.state_labels[r], "n": n_r, "vol_mean": vol_mean,
                         "t": t_nw, "sig": sig, "enough": enough})
        log(f"    {clf.state_labels[r]:12s} {n_r:5d} {vol_mean:10.4f} {vol_std:8.4f} "
            f"{vol_mean - global_mean_vol:+15.4f} {t_nw:+6.2f} {'***' if sig else '':>5s} {str(enough):>15s}")

    # --- Veredicto pre-registrado ---
    log("\n--- VEREDICTO (§12, pre-registrado) ---")
    enough = [v for v in verdicts if v["enough"]]
    log(f"Regímenes con muestra suficiente (n>={MIN_SAMPLE_PER_REGIME}): "
        f"{[v['name'] for v in enough] or 'NINGUNO'}")
    if not enough:
        log("=> Sin muestra suficiente para decidir. RÉGIMEN_VOLATILIDAD: NO EVALUABLE")
    else:
        any_sig = any(v["sig"] for v in enough)
        if any_sig:
            sig_names = [v["name"] for v in enough if v["sig"]]
            log(f"=> Régimen(es) con vol realizada significativamente distinta de la media global: {sig_names}")
            log("RÉGIMEN_VOLATILIDAD: SEÑAL DE RIESGO REAL (candidato para vol-targeting)")
        else:
            log("=> Ningún régimen con muestra suficiente difiere significativamente de la vol media global.")
            log("RÉGIMEN_VOLATILIDAD: NO APORTA (ni retorno ni riesgo)")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
