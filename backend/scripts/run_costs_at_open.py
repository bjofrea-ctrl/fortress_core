"""Runner M4: espera la apertura del mercado y corre la medición de costos paper.

Motivo: las órdenes market de paper solo fillean con el mercado abierto
(422 "extended hours order must be DAY or GTC limit orders" fuera de rueda;
ver smoke test del domingo 2026-08-17). La medición exige fills contra NBBO
real, así que no se puede adelantar: se corre al open.

Mecánica:
  1. Poll de GET /v2/clock cada POLL_SECONDS hasta is_open=true (con deadline).
  2. Al abrir: compra 1 unidad de cada símbolo del universo (lado buy) y
     después vende las posiciones abiertas (lado sell) — dos rondas de fills
     reales para medir slippage de entrada y de salida.
  3. Los artefactos y la DB los escribe scripts/measure_execution_costs.py
     (contrato M4), uno por ronda.

Uso (desde backend/):
  .venv/bin/python -m scripts.run_costs_at_open [--max-wait-hours 20] [--qty 1]

Credenciales: lee app.config.settings (que carga backend/.env) y las exporta
al entorno para el chequeo os.environ del script de medición. NUNCA se imprimen.
"""
import argparse
import datetime
import os
import sys
import time

from app.config import settings

POLL_SECONDS = 60
CLOCK_URL = "https://paper-api.alpaca.markets/v2/clock"


def _clock(session):
    r = session.get(CLOCK_URL, timeout=20)
    r.raise_for_status()
    return r.json()


def wait_for_open(max_wait_hours: float) -> bool:
    import requests

    s = requests.Session()
    s.headers.update(
        {
            "APCA-API-KEY-ID": os.environ["ALPACA_PAPER_API_KEY"],
            "APCA-API-SECRET-KEY": os.environ["ALPACA_PAPER_SECRET_KEY"],
        }
    )
    deadline = time.time() + max_wait_hours * 3600
    try:
        while time.time() < deadline:
            try:
                data = _clock(s)
                if data.get("is_open"):
                    return True
                print(
                    f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] mercado cerrado, "
                    f"next_open={data.get('next_open')}; espero {POLL_SECONDS}s",
                    flush=True,
                )
            except Exception as exc:  # red inestable: seguir esperando, no abortar
                print(f"[poll] error transitorio: {exc}", flush=True)
            time.sleep(POLL_SECONDS)
        return False
    finally:
        s.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R1 M4 al open del mercado (paper).")
    parser.add_argument("--max-wait-hours", type=float, default=20.0)
    parser.add_argument("--qty", type=float, default=1.0)
    args = parser.parse_args(argv)

    if not settings.ALPACA_PAPER_API_KEY or not settings.ALPACA_PAPER_SECRET_KEY:
        print("Faltan credenciales paper en backend/.env (ALPACA_PAPER_API_KEY/_SECRET_KEY).",
              file=sys.stderr)
        return 1
    os.environ["ALPACA_PAPER_API_KEY"] = settings.ALPACA_PAPER_API_KEY
    os.environ["ALPACA_PAPER_SECRET_KEY"] = settings.ALPACA_PAPER_SECRET_KEY

    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] M4 runner armado, esperando apertura...",
          flush=True)
    if not wait_for_open(args.max_wait_hours):
        print(f"No se abrió el mercado en {args.max_wait_hours:.0f}h — abortar.", file=sys.stderr)
        return 1

    from scripts.measure_execution_costs import main as measure_main

    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] MERCADO ABIERTO — ronda BUY", flush=True)
    rc_buy = measure_main(["--side", "buy", "--qty", str(args.qty)])
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] ronda SELL (cierra posiciones)", flush=True)
    rc_sell = measure_main(["--side", "sell", "--qty", str(args.qty)])
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] fin. rc_buy={rc_buy} rc_sell={rc_sell}",
          flush=True)
    return 0 if (rc_buy == 0 and rc_sell == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
