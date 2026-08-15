"""M4 — mide costos reales de ejecución vía Alpaca PAPER (script conductor).

ÚNICO propósito: MEDIR, no operar. Manda N órdenes market paper sobre el universo,
computa slippage = (fill - decision)/decision y persiste + deja el resumen al contrato
de salida de M4.

Salidas:
  - filas en SQLite (FORTRESS_COSTS_DB, default ./data/cache/execution_costs.db)
  - artefacto legible con timestamp en ./data/cache/measure_execution_costs_<ts>.txt

Uso (desde backend/):
  .venv/bin/python -m scripts.measure_execution_costs [--orders-per-symbol N] \
      [--symbols SPY,QQQ] [--side buy] [--qty 1]

Regla no negociable: PAPER únicamente. Sin credenciales paper configuradas termina con
un mensaje de QUÉ HARÍA FALTA (no inventa una medición ni bloquea el resto del módulo).
"""
import argparse
import datetime
import json
import os
import sys

from app.core.execution_costs import (
    AlpacaPaperClient,
    ConfigurationError,
    ExecutionCostRecorder,
    measure_slippage,
    summarize,
)

ARTIFACT_DIR = "./data/cache"

# Los 7 símbolos actuales del motor + NEW_UNIVERSE de scripts/fetch_universe_data.py
# (top-43 US por market cap). Se importa acá para que el universo viva en un solo lugar.
from scripts.fetch_universe_data import NEW_UNIVERSE  # noqa: E402

BASE_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def _universe(selected=None):
    if selected:
        return [s.strip().upper() for s in selected.split(",") if s.strip()]
    return BASE_SYMBOLS + NEW_UNIVERSE


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mide costos reales vía Alpaca PAPER.")
    parser.add_argument("--orders-per-symbol", type=int, default=1,
                        help="Órdenes market paper por símbolo (default 1).")
    parser.add_argument("--symbols", type=str, default="",
                        help="Subset de símbolos separados por coma (default: universo completo).")
    parser.add_argument("--side", type=str, default="buy", choices=["buy", "sell"])
    parser.add_argument("--qty", type=float, default=1.0)
    args = parser.parse_args(argv)

    symbols = _universe(args.symbols)
    if args.orders_per_symbol < 1:
        print("--orders-per-symbol debe ser >= 1.", file=sys.stderr)
        return 2

    # --- ¿Qué hace falta para medir? (doctrina #3: construir el caño, decir qué falta) ---
    missing = []

    def _env(name):
        v = os.environ.get(name, "")
        return v

    if not _env("ALPACA_PAPER_API_KEY") or not _env("ALPACA_PAPER_SECRET_KEY"):
        missing.append(
            "cuenta ALPACA PAPER (gratis): setear ALPACA_PAPER_API_KEY y "
            "ALPACA_PAPER_SECRET_KEY como variables de entorno / .env (NUNCA en código o chat)"
        )
    if missing:
        print("M4 — medición real NO configurada todavía.", file=sys.stderr)
        print("Hace falta: " + "; ".join(missing), file=sys.stderr)
        print("El módulo (app/core/execution_costs.py), sus tests y este script ya están", file=sys.stderr)
        print("construidos y verificados con mock; la medición viva corre cuando existan", file=sys.stderr)
        print("las credenciales paper.", file=sys.stderr)
        return 1

    try:
        client = AlpacaPaperClient()
    except ConfigurationError as exc:
        print(f"M4 — {exc}", file=sys.stderr)
        return 1

    db_path = os.environ.get("FORTRESS_COSTS_DB", f"{ARTIFACT_DIR}/execution_costs.db")
    recorder = ExecutionCostRecorder(db_path)
    try:
        for _ in range(args.orders_per_symbol):
            measure_slippage(client, recorder, symbols, qty=args.qty, side=args.side)
        records = recorder.records()
        summary = summarize(records)
    finally:
        recorder.close()
        client.close()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_path = f"{ARTIFACT_DIR}/measure_execution_costs_{ts}.txt"
    lines = [
        "=" * 80,
        "M4 — medición de costos reales (Alpaca PAPER)",
        f"Timestamp: {ts}  |  órdenes: {summary['n_ordenes']}  |  lado: {args.side}",
        "Slippage = (fill - decision)/decision | decision = último trade pre-orden",
        "=" * 80,
        "RESUMEN (contrato de salida M4):",
        json.dumps(summary, indent=2),
        "=" * 80,
        "ÓRDENES:",
    ]
    for r in records:
        lines.append(
            f"{r['date']}  {r['symbol']:6s} {r['side']:4s} "
            f"decision={r['price_decision']:.2f}  fill={r['price_fill']:.2f}  "
            f"slippage={r['slippage']:+.6f}  comisión={r['commission_frac']:.6f}"
        )
    with open(artifact_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")

    print(json.dumps(summary, indent=2))
    print(f"Artefacto: {artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
