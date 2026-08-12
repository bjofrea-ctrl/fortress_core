"""
PLAN_MEJORA_MATEMATICA §11 regla 2 — RE-MEDICIÓN del condicionamiento de régimen
sobre la SERIE DEL BASKET (2026-08-11/12).

Contexto: el trial (a) basket usa el régimen HMM SOLO como identificador; el
ajuste de exposición por régimen (+0.198 GOLDILOCKS / -0.173 DEFLATION, "macro
contra-régimen", citado en RESUMEN_VALIDACION_VARIABLES §5 y PLAN_SENTIMIENTO)
NO entra al pre-registro hasta re-medirse con la especificación correcta.

La medición original (Fase 2) tenía DOS defectos que esta re-medición corrige:
  1. Target pooled sobre el panel de 50 acciones (cada fila por símbolo) — mezcla
     la dimensión temporal con la transversal. Acá el target es UN solo activo:
     el retorno forward del basket equal-weight de los 50.
  2. Régimen con lookahead (§3.1): cada fila recibía el régimen del último día de
     toda la serie. Acá el régimen se etiqueta walk-forward (decodificación Viterbi
     sobre [2015, t], fit HMM <= 2024-12-31) — sin usar fechas futuras.

Pregunta pre-registrada: ¿el patrón "macro contra-régimen" sobrevive sobre la serie
del basket con la spec limpia?

Criterio de decisión PRE-REGISTRADO (lección §10 — umbrales desde el inicio):
  El condicionamiento de régimen ENTRA al pre-registro si, sobre el basket y con
  régimen limpio, se conserva el patrón de signos de la medición original en los
  regímenes con muestra suficiente (n >= 200 días de basket):
     - GOLDILOCKS: IC macro significativo > 0  (era +0.198)
     - DEFLATION:  IC macro significativo < 0  (era -0.173)
  con |t| = |IC| * sqrt(n_eff) > 2.0 (Newey-West, mismo aparato que diagnose_sentiment_oos).
  Si un régimen cambia de signo, pierde significancia, o el IC es degenerado
  (n < 200), el condicionamiento NO entra y (a) corre SOLO con ADX.

El script NO decide nada por sí mismo: escribe el artefacto con huella timestamp y
la interpretación la hace el §11 del plan. Ver regla §3.4: todo número se verifica
contra el artefacto.
"""
import datetime
import os
import math

import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.predictive_engine import PredictiveEngine
from app.core.probabilistic_engine import SignalQualityMetrics
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX",
                 "DX-Y.NYB", "GC=F", "SI=F", "CL=F", "HG=F"]
FIT_END = "2024-12-31"
START = "2019-01-01"
END = "2026-08-04"
HORIZON = 20
STRIDE_DAYS = 5
MIN_BASKET_MEMBERS = 40     # piso de miembros del basket en la fecha
MIN_SAMPLE_PER_REGIME = 200  # piso de observaciones (días) por régimen
REGIME_SIGN_EXPECTED = {0: +1, 1: -1, 2: -1, 3: -1}  # GOLDILOCKS+, resto contra


def _norm_pvalue(z: float) -> float:
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def significance_threshold(n: int) -> float:
    return 2.0 / np.sqrt(n)


def newey_west_neff_1d(x: np.ndarray, y: np.ndarray, horizon: int, stride: int) -> float:
    """n_eff Newey-West para series 1D (un solo activo = basket)."""
    if len(x) != len(y):
        return 30.0
    n = len(x)
    if n < 30:
        return 30.0
    z = (x - x.mean()) * (y - y.mean())
    L = int(np.ceil(horizon / stride))
    lag_max = min(L, n - 2)
    if lag_max < 1:
        return max(float(n), 30.0)
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (L + 1)
    denom = 1 + 2 * np.sum(w * rho)
    return max(n / max(denom, 1 + L), 30.0)


def label_regimes_walk_forward(clf: GlobalRegimeClassifier, price_data: dict) -> pd.Series:
    """Etiqueta cada fecha del basket con su régimen, decodificando Viterbi sobre
    [inicio, t] (sin fechas futuras) — idéntico a audit_regime_hmm.py."""
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


def build_basket_series(price_data: dict) -> pd.DataFrame:
    """Serie del basket equal-weight de los 50 símbolos (rebalanceo diario):
    retorno diario = media de retornos diarios de los miembros disponibles en la fecha.
    Devuelve columna 'basket' (nivel) y 'basket_ret' (retorno diario)."""
    closes = {s: d["close"] for s, d in price_data.items() if "close" in d and len(d) > 200}
    frame = pd.DataFrame(closes).sort_index()
    rets = frame.pct_change()
    # Piso de miembros: si faltan muchos, la fecha es de baja cobertura
    member_count = rets.notna().sum(axis=1)
    rets = rets.where(member_count >= MIN_BASKET_MEMBERS)
    basket_ret = rets.mean(axis=1).dropna()
    basket = (1 + basket_ret).cumprod()
    return pd.DataFrame({"basket": basket, "basket_ret": basket_ret})

def main():
    out_path = os.path.join("data", "cache",
                            f"regime_basket_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§11 regla 2 — RE-MEDICIÓN condicionamiento de régimen SOBRE LA SERIE DEL BASKET")
    log(f"Universo basket: {len(SYMBOLS)} símbolos (equal-weight, rebalanceo diario)")
    log(f"Horizonte {HORIZON}d | stride {STRIDE_DAYS}d | régimen HMM walk-forward (fit<={FIT_END})")
    log(f"Ventana: {START} -> {END} | piso miembros basket: {MIN_BASKET_MEMBERS}")
    log("Criterio: signos GOLDILOCKS>0 / DEFLATION<0 conservados con |t|>2 en n>=200")
    log("=" * 72)

    # --- Datos ---
    log("\nCargando datos...")
    market_data = load_universe(MACRO_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)

    macro_keys = {
        "DXY": "DX-Y.NYB", "gold": "GC=F", "silver": "SI=F", "TLT": "TLT",
        "SPY": "SPY", "oil": "CL=F", "copper": "HG=F",
    }
    macro_data = {}
    for k, v in macro_keys.items():
        df = market_data.get(v)
        if df is not None:
            macro_data[k] = df
    log(f"Macro disponible: {sorted(macro_data)}")

    # --- 1. Serie del basket ---
    basket_df = build_basket_series(price_data)
    log(f"\nBasket construido: {len(basket_df)} días, {START} -> {basket_df.index[-1]:%Y-%m-%d}")

    # --- 2. Fit HMM <= FIT_END, etiqueta walk-forward ---
    fit_data = {t: df[df.index <= pd.Timestamp(FIT_END)] for t, df in market_data.items()}
    clf = GlobalRegimeClassifier(n_states=4)
    clf.fit(fit_data)
    log(f"\nHMM fiteado con datos <= {FIT_END}")
    reg_series = label_regimes_walk_forward(clf, market_data)
    reg_series = reg_series.reindex(basket_df.index)


    # --- 3. Score macro compuesto + forward return del basket, por fecha strided ---
    engine = PredictiveEngine()
    rec = []  # {date, regime, macro_score, fwd}
    dates = basket_df.index
    n = len(dates)
    for i in range(0, n - HORIZON, STRIDE_DAYS):
        date = dates[i]
        regime = int(reg_series.loc[date]) if reg_series.loc[date] >= 0 else -1
        if regime < 0:
            continue
        truncated = {k: df[df.index <= date] for k, df in macro_data.items()}
        try:
            _, macro_score = engine._macro_signals(truncated)
        except Exception:
            continue
        if macro_score is None or math.isnan(macro_score):
            continue
        entry = basket_df["basket"].iloc[i]
        future = basket_df["basket"].iloc[i + HORIZON]
        fwd = future / entry - 1
        rec.append({"date": date, "regime": regime, "macro_score": macro_score, "fwd": fwd})
    rec = pd.DataFrame(rec)
    log(f"\nRegistros basket-vs-macro: {len(rec)} (estrided {STRIDE_DAYS}d, h={HORIZON}d)")

    # --- 4. IC por régimen ---
    log(f"\n    {'régimen':12s} {'n':>5s} {'IC':>9s} {'n_eff':>7s} {'t':>6s} {'sig':>4s} {'sign_ok':>7s}")
    verdicts = []
    for r in range(4):
        sub = rec[rec["regime"] == r]
        n_r = len(sub)
        if n_r == 0:
            log(f"    {clf.state_labels[r]:12s} {'0':>5s} {'-':>9s} {'-':>7s} {'-':>6s} {'-':>4s} {'-':>7s}")
            continue
        ic = SignalQualityMetrics.compute_ic(sub["macro_score"], sub["fwd"])
        rank_ic = SignalQualityMetrics.compute_rank_ic(sub["macro_score"], sub["fwd"])
        n_eff = newey_west_neff_1d(sub["macro_score"].to_numpy(), sub["fwd"].to_numpy(),
                                   HORIZON, STRIDE_DAYS)
        t = ic * math.sqrt(n_eff) if n_eff >= 30 else float("nan")
        sig = not math.isnan(t) and abs(t) > 2.0
        enough = n_r >= MIN_SAMPLE_PER_REGIME
        exp = REGIME_SIGN_EXPECTED[r]
        sign_ok = enough and (ic * exp > 0)
        verdicts.append({"r": r, "name": clf.state_labels[r], "n": n_r, "ic": ic,
                         "rank_ic": rank_ic, "n_eff": n_eff, "t": t, "sig": sig,
                         "enough": enough, "sign_ok": sign_ok})
        log(f"    {clf.state_labels[r]:12s} {n_r:5d} {ic:+9.4f} {n_eff:7.0f} "
            f"{t if not math.isnan(t) else float('nan'):+6.2f} "
            f"{'***' if sig else '':>4s} {str(sign_ok):>7s}")


    # --- 5. Veredicto pre-registrado ---
    log("\n--- VEREDICTO (§11 regla 2, pre-registrado) ---")
    enough = [v for v in verdicts if v["enough"]]
    log(f"Regímenes con muestra suficiente (n>={MIN_SAMPLE_PER_REGIME}): "
        f"{[v['name'] for v in enough] or 'NINGUNO'}")
    if not enough:
        log("=> Sin muestra suficiente para decidir. (a) corre SOLO con ADX "
            "(condicionamiento de régimen NO entra hasta re-medir con más datos).")
        log("CONDICIONAMIENTO_RÉGIMEN: NO ENTRA (sin muestra)")
    else:
        any_sign_flip = any(v["enough"] and not v["sign_ok"] for v in enough)
        gold = next((v for v in enough if v["name"] == "GOLDILOCKS"), None)
        defl = next((v for v in enough if v["name"] == "DEFLATION"), None)
        gold_ok = gold is not None and gold["sign_ok"] and gold["sig"]
        defl_ok = defl is not None and defl["sign_ok"] and defl["sig"]
        if any_sign_flip:
            log("=> Un régimen con muestra suficiente cambió de signo vs lo esperado.")
            log("CONDICIONAMIENTO_RÉGIMEN: NO ENTRA (cambio de signo)")
        elif gold_ok and defl_ok:
            log("=> Patrón conservado: GOLDILOCKS>0 y DEFLATION<0, ambos |t|>2 en n>=200.")
            log("CONDICIONAMIENTO_RÉGIMEN: ENTRA al pre-registro §11 (re-medido sobre basket)")
        else:
            reasons = []
            if not gold_ok:
                reasons.append(f"GOLDILOCKS{' ok' if gold and gold['sign_ok'] else ' no convence'}")
            if not defl_ok:
                reasons.append(f"DEFLATION{' ok' if defl and defl['sign_ok'] else ' no convence'}")
            log(f"=> Patrón incompleto: {', '.join(reasons)}.")
            log("CONDICIONAMIENTO_RÉGIMEN: NO ENTRA (patrón incompleto)")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()

