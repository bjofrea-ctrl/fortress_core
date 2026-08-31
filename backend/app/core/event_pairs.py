"""Event-driven pairs trade: long/short discrecional (NO integrado al motor sistematico).

Ejemplo de uso: shock exogeno (terremoto, huracan) → comprar CAT (long) y vender
en corto TRV (aseguradora con exposicion concentrada en la zona).

DISEÑO:
- Herramienta/infraestructura discrecional, NO un trial estadistico con reclamo de edge.
- Fuera de alcance: signal_engine.py, NEW_UNIVERSE, trial_registry.py, pipeline_daily_signal.py.
- Ambas patas se ejecutan via AlpacaPaperClient (paper trading, cuenta margin-enabled).
- Registro en signal_ledger.py con qty negativo para la pata corta (el esquema lo soporta).
- Calculo de P&L: long = (sell - buy) / buy; short = (buy - sell) / sell (inverso).

USO:
  cd backend && .venv/bin/python -m scripts.event_pairs \\
      --long CAT --short TRV --qty 10 --reason "terremoto California"

  # O directamente (sin wrapper):
  cd backend && .venv/bin/python -m app.core.event_pairs \\
      --long CAT --short TRV --qty 10
"""
import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.config import settings


@dataclass
class PairTrade:
    """Resultado de un pairs trade completo (ambas patas)."""
    symbol_long: str
    symbol_short: str
    qty_long: float
    qty_short: float
    entry_date: str
    long_fill: Optional[float] = None
    short_fill: Optional[float] = None
    long_signal_id: str = ""
    short_signal_id: str = ""
    reason: str = ""
    error: Optional[str] = None


def _make_signal_id(symbol: str, date: str, side: str) -> str:
    """Signal_id determinista para pares event-driven."""
    return f"pair_{symbol}_{side}_{date}"


def open_pair(
    client: Any,
    ledger: Any,
    symbol_long: str,
    symbol_short: str,
    qty_long: float,
    qty_short: float,
    reason: str = "",
    entry_date: Optional[str] = None,
) -> PairTrade:
    """Ejecuta ambas patas de un pairs trade y las registra en el ledger.

    Args:
        client: AlpacaPaperClient (o fake con submit_market_order).
        ledger: SignalLedger (o fake con open_order).
        symbol_long: Símbolo de la pata larga (ej. CAT).
        symbol_short: Símbolo de la pata corta (ej. TRV).
        qty_long: Cantidad de acciones a comprar (long).
        qty_short: Cantidad de acciones a vender en corto.
        reason: Razón del trade (para el ledger).
        entry_date: Fecha de entrada (default: hoy).

    Returns:
        PairTrade con el resultado de ambas patas.
    """
    if entry_date is None:
        entry_date = dt.date.today().isoformat()

    trade = PairTrade(
        symbol_long=symbol_long,
        symbol_short=symbol_short,
        qty_long=qty_long,
        qty_short=qty_short,
        entry_date=entry_date,
        reason=reason,
    )

    # Pata larga: BUY
    long_sid = _make_signal_id(symbol_long, entry_date, "long")
    trade.long_signal_id = long_sid
    try:
        order_long = client.submit_market_order(symbol_long, qty_long, "buy")
        trade.long_fill = float(order_long["filled_avg_price"])
        ledger.open_order(
            signal_id=long_sid,
            symbol=symbol_long,
            entry_date=entry_date,
            qty=qty_long,
            open_fill_price=trade.long_fill,
            factors={"pair_trade": True, "leg": "long", "reason": reason},
        )
    except Exception as exc:
        trade.error = f"long_error: {str(exc)[:200]}"
        return trade

    # Pata corta: SELL (short)
    short_sid = _make_signal_id(symbol_short, entry_date, "short")
    trade.short_signal_id = short_sid
    try:
        order_short = client.submit_market_order(symbol_short, qty_short, "sell")
        trade.short_fill = float(order_short["filled_avg_price"])
        ledger.open_order(
            signal_id=short_sid,
            symbol=symbol_short,
            entry_date=entry_date,
            qty=-qty_short,  # negativo para corto
            open_fill_price=trade.short_fill,
            factors={"pair_trade": True, "leg": "short", "reason": reason},
        )
    except Exception as exc:
        trade.error = f"short_error: {str(exc)[:200]}"
        return trade

    return trade


def close_pair(
    client: Any,
    ledger: Any,
    trade: PairTrade,
    exit_date: Optional[str] = None,
) -> PairTrade:
    """Cierra ambas patas de un pairs trade.

    Args:
        client: AlpacaPaperClient.
        ledger: SignalLedger.
        trade: PairTrade abierto (con long_signal_id y short_signal_id).
        exit_date: Fecha de salida (default: hoy).

    Returns:
        PairTrade actualizado con fills de salida y P&L.
    """
    if exit_date is None:
        exit_date = dt.date.today().isoformat()

    # Cerrar pata larga: SELL
    try:
        order_long = client.submit_market_order(
            trade.symbol_long, trade.qty_long, "sell"
        )
        close_fill_long = float(order_long["filled_avg_price"])
        pnl_r_long = ((close_fill_long * (1 - 0.001)) / (trade.long_fill * (1 + 0.001))) - 1.0
        ledger.close_order(
            signal_id=trade.long_signal_id,
            exit_date=exit_date,
            exit_reason="PAIR_CLOSE",
            pnl_r=round(pnl_r_long, 6),
            close_fill_price=close_fill_long,
        )
    except Exception as exc:
        trade.error = f"close_long_error: {str(exc)[:200]}"
        return trade

    # Cerrar pata corta: BUY (cover)
    try:
        order_short = client.submit_market_order(
            trade.symbol_short, trade.qty_short, "buy"
        )
        close_fill_short = float(order_short["filled_avg_price"])
        # P&L corto: (entry - exit) / entry (inverso del long)
        pnl_r_short = ((trade.short_fill * (1 - 0.001)) / (close_fill_short * (1 + 0.001))) - 1.0
        ledger.close_order(
            signal_id=trade.short_signal_id,
            exit_date=exit_date,
            exit_reason="PAIR_CLOSE",
            pnl_r=round(pnl_r_short, 6),
            close_fill_price=close_fill_short,
        )
    except Exception as exc:
        trade.error = f"close_short_error: {str(exc)[:200]}"
        return trade

    return trade


def pnl_summary(trade: PairTrade) -> Dict[str, Any]:
    """Calcula el P&L combinado de un pairs trade cerrado."""
    if trade.long_fill is None or trade.short_fill is None:
        return {"error": "trade_incomplete"}

    # P&L long (ya calculado en close_pair si se cerró)
    # P&L short (ya calculado en close_pair si se cerró)
    # Para un resumen, usamos los fills de entrada
    long_notional = trade.long_fill * trade.qty_long
    short_notional = trade.short_fill * trade.qty_short

    return {
        "symbol_long": trade.symbol_long,
        "symbol_short": trade.symbol_short,
        "qty_long": trade.qty_long,
        "qty_short": trade.qty_short,
        "long_fill": trade.long_fill,
        "short_fill": trade.short_fill,
        "long_notional": round(long_notional, 2),
        "short_notional": round(short_notional, 2),
        "net_exposure": round(long_notional - short_notional, 2),
        "reason": trade.reason,
    }


# CLI ----------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--long", required=True, help="Símbolo pata larga (ej. CAT)")
    parser.add_argument("--short", required=True, help="Símbolo pata corta (ej. TRV)")
    parser.add_argument("--qty", type=float, required=True, help="Cantidad por pata")
    parser.add_argument("--reason", default="", help="Razón del trade")
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime, no ejecuta")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(f"DRY RUN: long {args.long} x{args.qty} / short {args.short} x{args.qty}")
        print(f"Reason: {args.reason or '(none)'}")
        print("No se ejecuta nada en dry-run.")
        return 0

    from app.core.execution_costs import AlpacaPaperClient
    from app.core.signal_ledger import SignalLedger

    client = AlpacaPaperClient(
        api_key=settings.ALPACA_PAPER_API_KEY,
        secret_key=settings.ALPACA_PAPER_SECRET_KEY,
    )
    ledger = SignalLedger()

    trade = open_pair(
        client=client,
        ledger=ledger,
        symbol_long=args.long,
        symbol_short=args.short,
        qty_long=args.qty,
        qty_short=args.qty,
        reason=args.reason,
    )

    if trade.error:
        print(f"ERROR: {trade.error}")
        return 1

    print(f"Pair opened: {trade.symbol_long} x{trade.qty_long} @ {trade.long_fill}")
    print(f"             {trade.symbol_short} x{trade.qty_short} @ {trade.short_fill}")
    print(f"Signal IDs: {trade.long_signal_id}, {trade.short_signal_id}")

    summary = pnl_summary(trade)
    print(f"Net exposure: ${summary['net_exposure']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
