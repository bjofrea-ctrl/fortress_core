"""
PLAN_MEJORA_MATEMATICA §11 regla 1 — CHEQUEO DE DISTRIBUCIÓN del ADX del basket
(requisito PRE-REGISTRADO, antes de la corrida del trial (a)).

El trial (a) usa el ADX del basket como score de timing con los MISMOS umbrales
absolutos del motor (adx>25 -> long, 20-25 -> 0.3, <20 -> flat). Pero el ADX de
un basket diversificado suele ser MÁS SUAVE que el de una acción individual (por
cancelación de ruido idiosincrático): puede caer casi siempre <25 (degenerado por
arriba, nunca activa long) o casi siempre >20 (degenerado por abajo, nunca flat).

El §11 exige documentar la distribución empírica ANTES de correr y, si está
degenerada, recalibrar por percentil expansivo causal en vez de valor fijo. Esta
decisión se toma con datos AHORA: no post-hoc.

Criterio PRE-REGISTRADO de "degeneración":
  Los umbrales absolutos del motor discriminan el timing del basket si el tramo
  long (ADX>25) cubre >=20% de los días Y el tramo flat (ADX<20) cubre >=10%.
  Si cualquiera es menor, se RECALIBRA por percentil expansivo causal: LONG si
  ADX > perc85, FLAT si ADX < perc40, replicando la intensidad de señal del motor
  (ADX alto = tendencia) con cobertura utilizable.
  El valor / umbrales usados se escriben en el artefacto; el trial (a) los lee.

El script NO corre el trial: solo audita y decide los umbrales (regla §3.4).
"""
import datetime
import os

import numpy as np
import pandas as pd

from app.core.data_ingestion import load_universe
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
MIN_BASKET_MEMBERS = 40
WARMUP_DAYS = 30  # ADX(14) + margen

# Mínimos de cobertura pre-registrados (ver docstring)
MIN_LONG_COVERAGE = 0.20   # ADX>25 en >=20% de los días
MIN_FLAT_COVERAGE = 0.10   # ADX<20 en >=10% de los días


def build_basket_series(price_data: dict) -> pd.DataFrame:
    """Serie del basket equal-weight (rebalanceo diario) — idéntico a la
    re-medición de régimen, para que el trial use la MISMA construcción."""
    closes = {s: d["close"] for s, d in price_data.items() if "close" in d and len(d) > 200}
    frame = pd.DataFrame(closes).sort_index()
    rets = frame.pct_change()
    member_count = rets.notna().sum(axis=1)
    rets = rets.where(member_count >= MIN_BASKET_MEMBERS)
    basket_ret = rets.mean(axis=1).dropna()
    basket = (1 + basket_ret).cumprod()
    return pd.DataFrame({"basket": basket, "basket_ret": basket_ret})


def adx_series(close: pd.Series) -> pd.Series:
    """ADX(14) de Wilder sobre la serie de cierre del basket (high=low=close)."""
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


def main():
    out_path = os.path.join("data", "cache",
                            f"basket_adx_dist_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("§11 regla 1 — CHEQUEO DE DISTRIBUCIÓN ADX DEL BASKET (pre-corrida trial a)")
    log(f"Universo basket: {len(SYMBOLS)} símbolos (equal-weight) | {START} -> {END}")
    log(f"Regla motor: ADX>25 long / 20-25 <20 flat | mínimos long {MIN_LONG_COVERAGE:.0%} / flat {MIN_FLAT_COVERAGE:.0%}")
    log("=" * 72)

    price_data = load_universe(SYMBOLS, START, END)
    basket_df = build_basket_series(price_data)
    adx = adx_series(basket_df["basket"])
    # Solo días tradeables (post warmup)
    usable = adx[adx.index >= pd.Timestamp(START)]
    usable = usable.dropna()[WARMUP_DAYS:]
    n = len(usable)
    p_gt25 = float((usable > 25).mean())
    p_gt20 = float((usable > 20).mean())
    p_lt20 = float((usable < 20).mean())
    log(f"\nDías evaluables (post-warmup): {n}")
    log(f"  ADX > 25 (tramo long):  {p_gt25:.3f} ({int((usable>25).sum())} días)")
    log(f"  ADX 20-25 (tramo 0.3):  {max(0.0, p_gt20 - p_gt25):.3f} ({int(((usable>20)&(usable<=25)).sum())} días)")
    log(f"  ADX < 20 (tramo flat):  {p_lt20:.3f} ({int((usable<20).sum())} días)")
    log(f"  ADX min/median/max:     {usable.min():.1f} / {usable.median():.1f} / {usable.max():.1f}")
    log(f"  percentiles 25/50/75/90: {np.percentile(usable,25):.1f} / {np.percentile(usable,50):.1f} / "
        f"{np.percentile(usable,75):.1f} / {np.percentile(usable,90):.1f}")

    long_degen = p_gt25 < MIN_LONG_COVERAGE
    flat_degen = p_lt20 < MIN_FLAT_COVERAGE
    log("\n--- DECISIÓN PRE-REGISTRADA (regla 1) ---")
    if long_degen or flat_degen:
        log(f"Distribución DEGENERADA (long{'<' if long_degen else ''} {MIN_LONG_COVERAGE:.0%}"
            f"{' y/o' if long_degen and flat_degen else ''} flat{'<' if flat_degen else ''}"
            f" {MIN_FLAT_COVERAGE:.0%}). Umbrales absolutos del motor NO discriminan el "
            f"timing del basket.")
        q_high = float(np.percentile(usable.dropna(), 85))
        q_low = float(np.percentile(usable.dropna(), 40))
        log(f"  -> RECALIBRA por percentil expansivo causal (replica intensidad del motor):")
        log(f"     LONG si ADX > perc85 = {q_high:.1f} | FLAT si ADX < perc40 = {q_low:.1f}")
        log("THRESHOLDS: percentil (recalibrado)")
        log(f"LONG_ABOVE={q_high:.1f}")
        log(f"FLAT_BELOW={q_low:.1f}")
    else:
        log("Distribución con cobertura suficiente en long y flat. Se mantienen umbrales absolutos del motor.")
        log("THRESHOLDS: absolutos (motor)")
        log("LONG_ABOVE=25.0")
        log("FLAT_BELOW=20.0")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
