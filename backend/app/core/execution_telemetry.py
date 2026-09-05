"""Telemetría de ejecución por orden (A5 — PLAN_REMEDIO_BRECHAS_20260903) — fortress.db.

Libro de costos propio: una fila por ORDEN enviada por el pipeline diario
(paper), con el precio de decisión contra el que se midió, el fill real devuelto
por el broker y el slippage implícito `slippage_implicit = (fill − decision) /
decision`. Remedia la brecha #4 (ejecución medida): el costo vigente pasa de
supuesto (§33: slippage_referencia 0.05%/lado) a MEDIDO cuando la tabla acumule
N≥30 fills.

Diseño (patrón signal_ledger.py): módulo aparte, tabla propia en fortress.db,
sqlite3.connect por método (no hay infra compartible más allá de la ruta).
APPEND-ONLY por diseño — cada fila es un evento de ejecución real, no un estado:
una orden enviada dos veces son dos fills reales y ambos pertenecen al libro.
La idempotencia del pipeline vive en plan_enter/ledger (skip de sids ya
registrados), no acá.

Separación mecanismo vs evidencia (condición (b) del gate 2026-08-25): las
órdenes de checkpoint (chkpt__) se registran con checkpoint_override=1; los
reportes (scripts/execution_cost_report.py) NUNCA las mezclan con las oficiales.
"""
import sqlite3
from typing import Any, Dict, List, Optional

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS execution_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_ref DATE NOT NULL,
    phase TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    decision_price REAL,
    fill_price REAL,
    slippage_implicit REAL,
    checkpoint_override INTEGER NOT NULL DEFAULT 0,
    client_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',
    error TEXT
)
"""


def compute_slippage(decision_price: Optional[float],
                     fill_price: Optional[float]) -> Optional[float]:
    """slippage_implicit = (fill − decision) / decision.

    None (no cero) si falta alguno de los dos o decision <= 0 — una fila sin
    precio de decisión medible no produce slippage, y reportarlo como 0.0
    contaminaría la distribución.
    """
    if decision_price is None or fill_price is None:
        return None
    if decision_price <= 0:
        return None
    return (float(fill_price) - float(decision_price)) / float(decision_price)


class ExecutionTelemetry:
    def __init__(self, db_path: str = "fortress.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_SCHEMA_SQL)

    def record(
        self,
        *,
        phase: str,
        run_ref: str,
        symbol: str,
        side: str,
        qty: float,
        decision_price: Optional[float],
        fill_price: Optional[float],
        checkpoint_override: bool = False,
        client_order_id: Optional[str] = None,
        status: str = "submitted",
        error: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> None:
        """INSERT append-only de un evento de ejecución (orden enviada).

        `status='error'` registra el intento fallido (fill_price NULL) — el
        futuro kill-switch (A3: fill rate < 80% del día) necesita contar
        intentos, no solo fills.
        """
        from datetime import datetime

        ts = ts or datetime.now().isoformat(timespec="seconds")
        slippage = compute_slippage(decision_price, fill_price)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO execution_telemetry
                    (ts, run_ref, phase, symbol, side, qty,
                     decision_price, fill_price, slippage_implicit,
                     checkpoint_override, client_order_id, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, str(run_ref), phase, symbol, side, float(qty),
                 (float(decision_price) if decision_price is not None else None),
                 (float(fill_price) if fill_price is not None else None),
                 slippage,
                 int(bool(checkpoint_override)),
                 client_order_id,
                 status,
                 (str(error)[:200] if error else None)),
            )

    def fetch(
        self,
        symbol: Optional[str] = None,
        phase: Optional[str] = None,
        only_official: bool = False,
    ) -> List[Dict[str, Any]]:
        """Filas como dicts (cronológico), opcionalmente filtradas.

        `only_official=True` excluye las órdenes de checkpoint (mecanismo) —
        la separación que todo reporte de costos debe respetar.
        """
        sql = "SELECT * FROM execution_telemetry"
        where, params = [], []
        if symbol is not None:
            where.append("symbol = ?")
            params.append(symbol)
        if phase is not None:
            where.append("phase = ?")
            params.append(phase)
        if only_official:
            where.append("checkpoint_override = 0")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        return [{k: row[k] for k in row.keys()} for row in rows]

    def count(self, only_official: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM execution_telemetry"
        if only_official:
            sql += " WHERE checkpoint_override = 0"
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(sql).fetchone()[0]

    def close(self) -> None:
        """No-op por compatibilidad de interfaz (matchea SignalLedger)."""
