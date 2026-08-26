"""Ledger de señales etiquetadas por barreras (T1.6) — persistencia en fortress.db.

Guarda una fila por señal generada por `barrier_labeling.label_symbol` (cuando se
le pasa `ledger`) para que `BayesianOnlineUpdater` aprenda de outcomes más
granulares que el `won = pnl > 0` binario: cada fila registra la categoría de
salida (la taxonomía fina de barrier_labeling) y el retorno en unidades de
riesgo (pnl_r = retorno neto / position_stop del régimen).

Diseño: módulo aparte de config_registry.py (T1.5). Ambos escriben en fortress.db
pero con tablas y contratos distintos — config_history es un registro de
parámetros versionados append-only; signal_ledger es un registro de outcomes,
upsert por signal_id (re-etiquetar el mismo panel no duplica filas). Se repite la
convención de conexión (`sqlite3.connect(db_path)` en cada método); no hay
infraestructura compartible más allá de la ruta de la DB.
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signal_ledger (
    signal_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    entry_date DATE NOT NULL,
    exit_date DATE NOT NULL,
    exit_reason TEXT NOT NULL,
    pnl_r REAL NOT NULL,
    factors_json TEXT NOT NULL,
    regime_state INTEGER NOT NULL
)
"""

# Migración aditiva (Frente 2, Semana 1): permitir filas de PAPER ORDER en el
# mismo ledger — `record()` (T1.6) sigue siendo la API de outcomes; los dos
# estados de ciclo de vida (open/closed) se agregan sin borrar columnas ni tocar
# datos existentes. `status` distingue orden abierta (closure pendiente) de
# cerrada; las columnas de fill datean el P&L real de la orden de papel.
_NEW_COLUMNS = {
    "status": "ALTER TABLE signal_ledger ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
    "open_fill_price": "ALTER TABLE signal_ledger ADD COLUMN open_fill_price REAL",
    "close_fill_price": "ALTER TABLE signal_ledger ADD COLUMN close_fill_price REAL",
    "qty": "ALTER TABLE signal_ledger ADD COLUMN qty REAL",
}


class SignalLedger:
    def __init__(self, db_path: str = "fortress.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_SCHEMA_SQL)
            # migración robusta: detecta por PRAGMA qué columnas faltan y agrega
            # solo esas (ALTER ... ADD COLUMN falla en lote si una ya existe).
            existing = {r[1] for r in
                        conn.execute("PRAGMA table_info(signal_ledger)").fetchall()}
            for col, ddl in _NEW_COLUMNS.items():
                if col not in existing:
                    conn.execute(ddl)

    def record(
        self,
        signal_id: str,
        symbol: str,
        entry_date: str,
        exit_date: str,
        exit_reason: str,
        pnl_r: float,
        factors: Optional[Dict[str, Any]] = None,
        regime_state: int = 0,
    ) -> None:
        """Inserta o reemplaza la fila de una señal (idempotente por signal_id).

        Upsert con ON CONFLICT (no INSERT OR REPLACE + COALESCE en VALUES:
        SQLite no resuelve referencias a columnas de la tabla en el VALUES,
        y REPLACE borraría los fills de una orden de papel ya registrada).
        Re-etiquetar el mismo panel actualiza el outcome y PRESERVA
        open_fill_price/close_fill_price/qty si estaban.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO signal_ledger
                    (signal_id, symbol, entry_date, exit_date, exit_reason,
                     pnl_r, factors_json, regime_state, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'closed')
                ON CONFLICT(signal_id) DO UPDATE SET
                    symbol = excluded.symbol,
                    entry_date = excluded.entry_date,
                    exit_date = excluded.exit_date,
                    exit_reason = excluded.exit_reason,
                    pnl_r = excluded.pnl_r,
                    factors_json = excluded.factors_json,
                    regime_state = excluded.regime_state,
                    status = 'closed'
                """,
                (signal_id, symbol, entry_date, exit_date, exit_reason,
                 float(pnl_r), json.dumps(factors or {}), int(regime_state)),
            )

    def open_order(
        self,
        signal_id: str,
        symbol: str,
        entry_date: str,
        qty: float,
        open_fill_price: float,
        factors: Optional[Dict[str, Any]] = None,
        regime_state: int = 0,
    ) -> None:
        """Abre una orden de papel en el ledger (cierre pendiente).

        La fila nace `status='open'` con `pnl_r=0` y `exit_date=entry_date` (el
        NOT NULL del esquema) — el cierre real reemplaza esos campos. Idempotente
        por `signal_id` (re-abrir la misma orden no duplica).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO signal_ledger
                    (signal_id, symbol, entry_date, exit_date, exit_reason,
                     pnl_r, factors_json, regime_state, status,
                     open_fill_price, close_fill_price, qty)
                VALUES (?, ?, ?, ?, 'OPEN', 0.0, ?, ?, 'open', ?, NULL, ?)
                """,
                (signal_id, symbol, entry_date, entry_date,
                 json.dumps(factors or {}), int(regime_state),
                 float(open_fill_price), float(qty)),
            )

    def close_order(
        self,
        signal_id: str,
        exit_date: str,
        exit_reason: str,
        pnl_r: float,
        close_fill_price: Optional[float] = None,
    ) -> None:
        """Cierra una orden abierta: completa salida, pnl_r y precio de cierre."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE signal_ledger SET
                    status = 'closed',
                    exit_date = ?,
                    exit_reason = ?,
                    pnl_r = ?,
                    close_fill_price = COALESCE(?, close_fill_price)
                WHERE signal_id = ?
                """,
                (exit_date, exit_reason, float(pnl_r), close_fill_price, signal_id),
            )

    def open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Órdenes de papel que siguen ABERTAS (cierre pendiente), para reconciliar."""
        sql = "SELECT * FROM signal_ledger WHERE status = 'open'"
        params: List[Any] = []
        if symbol is not None:
            sql += " AND symbol = ?"
            params.append(symbol)
        sql += " ORDER BY entry_date"
        return self._rows(sql, params)

    def fetch(
        self,
        symbol: Optional[str] = None,
        exit_reason: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Devuelve filas como dicts, opcionalmente filtradas por símbolo/categoría."""
        sql = "SELECT * FROM signal_ledger"
        where, params = [], []
        if symbol is not None:
            where.append("symbol = ?")
            params.append(symbol)
        if exit_reason is not None:
            where.append("exit_reason = ?")
            params.append(exit_reason)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY entry_date"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        return self._rows(sql, params)

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM signal_ledger").fetchone()[0]

    def _rows(self, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        """Helper: ejecuta una SELECT y devuelve filas como dicts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]

    def close(self) -> None:
        """No-op por compatibilidad de interfaz (matchea execution_costs)."""
