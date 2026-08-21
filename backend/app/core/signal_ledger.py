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


class SignalLedger:
    def __init__(self, db_path: str = "fortress.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_SCHEMA_SQL)

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
        """Inserta o reemplaza la fila de una señal (idempotente por signal_id)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO signal_ledger
                    (signal_id, symbol, entry_date, exit_date, exit_reason,
                     pnl_r, factors_json, regime_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (signal_id, symbol, entry_date, exit_date, exit_reason,
                 float(pnl_r), json.dumps(factors or {}), int(regime_state)),
            )

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
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM signal_ledger").fetchone()[0]
