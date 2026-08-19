"""Fase B de §32 (PLAN_MEJORA_MATEMATICA): predictividad de indicadores por franja.

Pregunta: ¿la correlación del momentum intraday y RSI(14) con el retorno forward
difiere materialmente entre franjas (APERTURA/MEDIA/CIERRE)? Data: parquets 1-min
de la Fase A (qqq_1min.parquet / spy_1min.parquet). Solo lectura.

Método (protocolo §4.1 adaptado a temporal por símbolo): por día y franja, Spearman
(indicator_t, retorno_forward_t) promediado sobre días, error Newey-West (lag 4).
Criterio §32: base para rotación si un indicador tiene |IC|>=0.02 y t>=2 en una
franja y |IC|<=0.01 o signo opuesto en otra.

Uso (desde backend/):
  .venv/bin/python -m scripts.diagnose_franjas_predictividad [--symbols QQQ,SPY]
"""
import argparse
import datetime
import json
import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")

FRANJAS = {
    "APERTURA": (9 * 60 + 30, 11 * 60 + 30),
    "MEDIA": (11 * 60 + 30, 14 * 60 + 0),
    "CIERRE": (14 * 60 + 0, 16 * 60 + 0),
}
WINDOWS = {"mom5": 5, "mom15": 15, "mom30": 30}
FWD = {"fwd5": 5, "fwd15": 15, "fwd30": 30}
NW_LAG = 4


def franja_of(hhmm: int) -> str:
    for name, (a, b) in FRANJAS.items():
        if a <= hhmm < b:
            return name
    return "FUERA"


def rsi14(close: pd.Series) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def nw_tstat(series: np.ndarray) -> float:
    """t-stat de la media con error estándar Newey-West (lag fijo)."""
    x = np.asarray(series, dtype=float)
    n = len(x)
    if n < 3:
        return 0.0
    mu = x.mean()
    gamma0 = np.mean((x - mu) ** 2)
    var = gamma0
    for k in range(1, NW_LAG + 1):
        if k >= n:
            break
        cov = np.mean((x[:-k] - mu) * (x[k:] - mu))
        var += 2 * (1 - k / (NW_LAG + 1)) * cov
    se = np.sqrt(max(var / n, 1e-18))
    return float(mu / se) if se > 0 else 0.0


def analyze_symbol(symbol: str) -> Dict:
    path = os.path.join(DATA_DIR, f"{symbol.lower()}_1min.parquet")
    df = pd.read_parquet(path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["hhmm"] = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    df["franja"] = df["hhmm"].map(franja_of)
    df["date"] = df["timestamp"].dt.date
    df = df[df["franja"] != "FUERA"].copy()

    close = df["close"]
    for name, k in WINDOWS.items():
        df[name] = close / close.shift(k) - 1
    df["rsi14"] = rsi14(close)
    for name, k in FWD.items():
        df[name] = close.shift(-k) / close - 1

    out = {"symbol": symbol, "n_barras": int(len(df)), "franjas": {}}
    for franja in FRANJAS:
        g = df[df["franja"] == franja]
        if len(g) < 500:
            continue
        f = {"indicadores": {}}
        for iname in list(WINDOWS) + ["rsi14"]:
            ic_daily = []
            hit_daily = []
            for _, day in g.groupby("date"):
                d = day.dropna(subset=[iname, "fwd5"])
                if len(d) < 20:
                    continue
                ic = d[iname].corr(d["fwd5"], method="spearman")
                if np.isnan(ic):
                    continue
                ic_daily.append(ic)
                sign = np.sign(d[iname]) == np.sign(d["fwd5"])
                hit_daily.append(sign.mean())
            if len(ic_daily) < 10:
                continue
            ic_arr = np.array(ic_daily)
            f["indicadores"][iname] = {
                "ic_medio": float(ic_arr.mean()),
                "t_stat_nw": nw_tstat(ic_arr),
                "n_dias": len(ic_arr),
                "hit_rate_medio": float(np.mean(hit_daily)),
            }
        out["franjas"][franja] = f
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fase B §32: predictividad por franja.")
    parser.add_argument("--symbols", default="QQQ,SPY")
    args = parser.parse_args(argv)

    results = []
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        print(f"[{sym}] analizando ...", file=sys.stderr)
        results.append(analyze_symbol(sym))

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact = os.path.join(DATA_DIR, f"franjas_predictividad_{ts}.txt")
    lines = [
        "=" * 80,
        "Fase B §32 — predictividad por franja (1-min, 2024-01-01 -> 2026-08-19)",
        f"Timestamp: {ts} | IC = Spearman diario promediado, t-stat Newey-West lag {NW_LAG}",
        "=" * 80,
        json.dumps(results, indent=2, default=str),
        "=" * 80,
    ]
    with open(artifact, "w") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    print(f"Artefacto: {artifact}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())