"""Fase A de §31 (PLAN_MEJORA_MATEMATICA): análisis exploratorio de franjas horarias.

Pregunta: ¿la microestructura de QQQ (Nasdaq-100) difiere por franja horaria ET?
Control: SPY (S&P 500). Barras 1-min vía API de Alpaca (IEX free, historial
verificado hasta 2019). Franjas: APERTURA 09:30-11:30, MEDIA 11:30-14:00,
CIERRE 14:00-16:00.

Naturaleza: análisis exploratorio (no trial de señal — no consume n_trials).
Criterio pre-registrado §31:
  - Estructura APARECE si volatilidad por barra difiere >= 1.5x entre franjas Y
    volumen medio por barra difiere >= 1.5x entre franjas.
  - Estructura EXPLOTABLE se evalúa en Fase B (solo si A da estructura).

Uso (desde backend/):
  .venv/bin/python -m scripts.diagnose_franjas_horarias [--start 2024-01-01] [--symbols QQQ,SPY]

Credenciales: backend/.env (ALPACA_PAPER_API_KEY/SECRET). Nunca se imprimen.
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
from typing import Dict, List

import pandas as pd
import requests
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")

FRANJAS = {
    "APERTURA": (9 * 60 + 30, 11 * 60 + 30),   # 09:30-11:30 ET
    "MEDIA": (11 * 60 + 30, 14 * 60 + 0),      # 11:30-14:00 ET
    "CIERRE": (14 * 60 + 0, 16 * 60 + 0),      # 14:00-16:00 ET
}

BARS_URL = "https://data.alpaca.markets/v2/stocks/{sym}/bars"
BATCH_DAYS = 90  # descarga en lotes de ~3 meses para no superar límites de la API


def _env(name: str) -> str:
    return os.environ.get(name, "")


def _headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": _env("ALPACA_PAPER_API_KEY"),
        "APCA-API-SECRET-KEY": _env("ALPACA_PAPER_SECRET_KEY"),
    }


def _as_et(ts_str: str) -> pd.Timestamp:
    """Convierte timestamp ISO (UTC) a ET naive."""
    return pd.Timestamp(ts_str).tz_convert(ET).tz_localize(None)


def download_1min(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Descarga 1-min bars paginando por ventanas de BATCH_DAYS días.

    La API paga por next_page_token; acá se usa start/end por lote (más simple y
    robusto). Devuelve DataFrame con columnas timestamp(ET naive), open, high,
    low, close, volume — SOLO barras en rueda regular (09:30-16:00 ET).
    """
    frames: List[pd.DataFrame] = []
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    session = requests.Session()
    session.headers.update(_headers())
    cursor = s
    while cursor < e:
        batch_end = min(cursor + pd.Timedelta(days=BATCH_DAYS), e)
        params = {
            "timeframe": "1Min",
            "start": cursor.strftime("%Y-%m-%dT00:00:00Z"),
            "end": batch_end.strftime("%Y-%m-%dT00:00:00Z"),
            "limit": 10000,
            "adjustment": "raw",
        }
        next_token = None
        while True:
            p = dict(params)
            if next_token:
                p["page_token"] = next_token
            r = session.get(BARS_URL.format(sym=symbol), params=p, timeout=30)
            r.raise_for_status()
            d = r.json()
            for b in d.get("bars", []):
                ts = _as_et(b["t"])
                hhmm = ts.hour * 60 + ts.minute
                if 9 * 60 + 30 <= hhmm < 16 * 60:
                    frames.append({
                        "timestamp": ts,
                        "open": float(b["o"]),
                        "high": float(b["h"]),
                        "low": float(b["l"]),
                        "close": float(b["c"]),
                        "volume": float(b["v"]),
                    })
            next_token = d.get("next_page_token")
            if not next_token:
                break
            time.sleep(0.25)
        cursor = batch_end
        time.sleep(0.25)
    if not frames:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(frames)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def franja_of(hhmm: int) -> str:
    for name, (a, b) in FRANJAS.items():
        if a <= hhmm < b:
            return name
    return "FUERA"


def analyze(df: pd.DataFrame, symbol: str) -> Dict:
    if df.empty:
        return {"symbol": symbol, "error": "sin datos"}
    df = df.copy()
    df["hhmm"] = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    df["franja"] = df["hhmm"].map(franja_of)
    df = df[df["franja"] != "FUERA"]
    df["ret"] = df["close"] / df["open"] - 1
    df["ret_abs"] = (df["close"] - df["open"]).abs() / df["open"]
    df["rango"] = (df["high"] - df["low"]) / df["close"]
    out = {"symbol": symbol, "n_barras": int(len(df)), "franjas": {}}
    for name in FRANJAS:
        g = df[df["franja"] == name]
        if g.empty:
            continue
        out["franjas"][name] = {
            "n_barras": int(len(g)),
            "ret_medio_por_barra": float(g["ret"].mean()),
            "ret_abs_medio_por_barra": float(g["ret_abs"].mean()),
            "volatilidad_por_barra": float(g["ret"].std()),
            "volumen_medio_por_barra": float(g["volume"].mean()),
            "rango_medio": float(g["rango"].mean()),
        }
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fase A §31: franjas horarias QQQ/SPY (1-min).")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--symbols", default="QQQ,SPY")
    args = parser.parse_args(argv)

    if not _env("ALPACA_PAPER_API_KEY") or not _env("ALPACA_PAPER_SECRET_KEY"):
        print("Faltan credenciales de data en backend/.env.", file=sys.stderr)
        return 1

    end = datetime.datetime.now(ET).strftime("%Y-%m-%d")
    results = []
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        print(f"[{sym}] descargando 1-min {args.start} -> {end} ...", file=sys.stderr)
        df = download_1min(sym, args.start, end)
        path = os.path.join(DATA_DIR, f"{sym.lower()}_1min.parquet")
        df.to_parquet(path, index=False)
        print(f"[{sym}] {len(df)} barras -> {path}", file=sys.stderr)
        results.append(analyze(df, sym))

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact = os.path.join(DATA_DIR, f"franjas_horarias_{ts}.txt")
    lines = [
        "=" * 80,
        "Fase A §31 — franjas horarias (1-min, Alpaca IEX)",
        f"Timestamp: {ts} | ventana: {args.start} -> {end} | franjas ET: 09:30-11:30 / 11:30-14:00 / 14:00-16:00",
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