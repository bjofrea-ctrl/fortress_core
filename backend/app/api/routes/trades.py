""""Rutas combinadas de trades: backtest histórico + paper trading real (signal_ledger).

Cada fila lleva un campo `origin` explícito ('backtest' | 'paper') para que el
frontend pueda distinguir el origen en la misma vista de tabla.

Convención de rutas: el endpoint original `/api/backtest/trades` se mantiene
intacto para compatibilidad; este router agrega `/api/trades/combined` con un
contrato unificado (ver GET /combined).
"""
import json
import os
import sqlite3
from typing import Any, Dict, List

from fastapi import APIRouter

router = APIRouter(prefix="/api/trades", tags=["trades"])

RESULTS_FILE = "data/backtest_results.json"
LEDGER_DB = "fortress.db"  # relativo a cwd=backend, misma convención que SignalLedger default

# Convención del pipeline diario (scripts/pipeline_daily_signal.py:139). Las filas
# con este prefijo en signal_id son inyecciones de CHECKPOINT para validar el
# mecanismo del tubo (OVERRIDE_MECANISMO — no es señal real) y NUNCA se mezclan
# con la vista de operaciones reales.
CHECKPOINT_SID_PREFIX = "chkpt__"


def _read_backtest_trades() -> List[Dict[str, Any]]:
    """Lee todos los trades del archivo de resultados del backtest.

    Returns lista de dicts con keys: symbol, entry_date, exit_date, entry_price,
    exit_price, shares, pnl, exit_reason. Vacía si no hay archivo.
    """
    if not os.path.exists(RESULTS_FILE):
        return []
    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)
    return data.get("trades", [])


def _read_ledger_trades() -> List[Dict[str, Any]]:
    """Lee trades del signal_ledger (paper trading real) desde fortress.db.

    Excluye las filas con signal_id prefijo `chkpt__` (CHECKPOINT_SID_PREFIX):
    son inyecciones de validación del mecanismo del tubo (OVERRIDE_MECANISMO),
    NO señales reales, y jamás se mezclan con la vista de operaciones.

    Returns lista de filas como dicts, normalizadas al contrato común:
      signal_id, symbol, entry_date, exit_date, exit_reason, pnl_r,
      open_fill_price, close_fill_price, qty, status, regime_state, factors_json.
    Vacía si la DB o la tabla no existen.
    """
    if not os.path.exists(LEDGER_DB):
        return []
    try:
        conn = sqlite3.connect(LEDGER_DB)
        # Verificar si la tabla existe
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "signal_ledger" not in tables:
            conn.close()
            return []
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT signal_id, symbol, entry_date, exit_date, exit_reason, "
            "pnl_r, open_fill_price, close_fill_price, qty, status, "
            "regime_state, factors_json "
            "FROM signal_ledger "
            # Excluir inyecciones de CHECKPOINT (validación del mecanismo del tubo,
            # NO señales reales — convención chkpt__ de pipeline_daily_signal.py).
            "WHERE signal_id NOT LIKE ? "
            "ORDER BY entry_date DESC",
            (CHECKPOINT_SID_PREFIX + "%",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except (sqlite3.Error, FileNotFoundError):
        return []


def _normalize_backtest_trade(t: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza un trade del backtest al contrato unificado con origin='backtest'.

    Calcula pnl_r (relativo) que no existe en el backtest original.
    """
    entry_price = float(t.get("entry_price", 0) or 0)
    exit_price = float(t.get("exit_price", 0) or 0)
    pnl_abs = float(t.get("pnl", 0) or 0)
    pnl_r = round((exit_price - entry_price) / entry_price, 6) if entry_price else 0.0
    return {
        "origin": "backtest",
        "symbol": str(t.get("symbol", "")),
        "entry_date": str(t.get("entry_date", ""))[:10],
        "exit_date": str(t.get("exit_date", ""))[:10],
        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),
        "shares": float(t.get("shares", 0) or 0),
        "pnl": round(pnl_abs, 2),
        "pnl_r": round(pnl_r, 4),
        "exit_reason": str(t.get("exit_reason", "")),
        "status": "closed",
        "signal_id": None,
    }


def _normalize_paper_trade(r: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza una fila del signal_ledger al contrato unificado con origin='paper'.

    Calcula el P&L absoluto en USD desde qty y precios de fill.
    pnl_r ya viene nativo del ledger.
    """
    qty = float(r.get("qty", 0) or 0)
    open_price = float(r.get("open_fill_price", 0) or 0)
    close_price = float(r.get("close_fill_price", 0) or 0)
    pnl_r = float(r.get("pnl_r", 0) or 0)
    status = str(r.get("status", "unknown"))
    if status == "open":
        # orden aún abierta: sin precio de salida ni P&L realizados
        pnl_abs = None
        close_price_clean = None
        pnl_r_clean = None
    else:
        # P&L absoluto: qty * (close - open) para posiciones long
        pnl_abs = round(qty * (close_price - open_price), 2)
        close_price_clean = round(close_price, 2)
        pnl_r_clean = round(pnl_r, 4)
    return {
        "origin": "paper",
        "symbol": str(r.get("symbol", "")),
        "entry_date": str(r.get("entry_date", ""))[:10],
        "exit_date": str(r.get("exit_date", ""))[:10],
        "entry_price": round(open_price, 2),
        "exit_price": close_price_clean,
        "shares": qty,
        "pnl": pnl_abs,
        "pnl_r": pnl_r_clean,
        "exit_reason": str(r.get("exit_reason", "")),
        "status": status,
        "signal_id": str(r.get("signal_id", "")),
    }


@router.get("/combined")
async def get_combined_trades(skip: int = 0, limit: int = 200):
    """Retorna trades de backtest + paper trading combinados, con origen explícito.

    - `skip`: cuántos saltar (paginación, default 0).
    - `limit`: máximo a devolver (default 200, 0 = todos).

    Cada fila lleva `origin: 'backtest' | 'paper'` para distinguir en la vista.
    Ordenado por entry_date descendente (más reciente primero).
    """
    bt_trades = _read_backtest_trades()
    paper_trades = _read_ledger_trades()

    # Normalizar ambos arrays
    all_trades: List[Dict[str, Any]] = []
    for t in bt_trades:
        all_trades.append(_normalize_backtest_trade(t))
    for r in paper_trades:
        all_trades.append(_normalize_paper_trade(r))

    # Ordenar por entry_date descendente (más reciente primero)
    # Fechas vacías van al final
    all_trades.sort(
        key=lambda x: x["entry_date"] or "",
        reverse=True,
    )

    total = len(all_trades)
    bt_total = len(bt_trades)
    paper_total = len(paper_trades)

    # Paginación
    if limit > 0:
        all_trades = all_trades[skip:skip + limit]

    return {
        "trades": all_trades,
        "total": total,
        "backtest_total": bt_total,
        "paper_total": paper_total,
    }
