"""Registro de parámetros versionado con reconstrucción point-in-time.

Adaptado del Adaptive Parameter Registry de indicAgent
(docs/foundation/adaptive-parameter-registry.md), simplificado SIN
Kafka/hot-reload — Fortress no es un servicio 24/7 y no lo necesita.

Tabla única en SQLite (fortress.db): config_history(key, value, version,
changed_by, reason, valid_from), PRIMARY KEY (key, version). Append-only:
set() solo hace INSERT, nunca UPDATE, para poder reconstruir el valor
vigente de un parámetro en cualquier fecha del pasado (get_at) y evitar
que un ajuste futuro contamine backtests de fechas anteriores.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.adaptive_risk import REGIME_THRESHOLDS

INITIAL_ESTIMATE = "initial_estimate"
_SEED_REASON = "Valor semilla de REGIME_THRESHOLDS (registro inicial)"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS config_history (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    version INTEGER NOT NULL,
    changed_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    PRIMARY KEY (key, version)
)
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(ts: datetime) -> datetime:
    """Normaliza un timestamp a timezone-aware UTC.

    Los timestamps naive (p.ej. pd.Timestamp de un panel sintético) se
    interpretan como UTC: así la comparación lexicográfica de los ISO
    strings almacenados es cronológicamente correcta y consistente."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _ts_to_iso(ts: datetime) -> str:
    return _to_utc(ts).isoformat()


class ConfigRegistry:
    def __init__(self, db_path: str = "fortress.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_SCHEMA_SQL)
            self._seed_initial_estimates(conn)

    def _seed_initial_estimates(self, conn: sqlite3.Connection) -> None:
        """Siembra REGIME_THRESHOLDS como versión 1 (changed_by="initial_estimate",
        misma provenance que indicAgent). Idempotente: solo inserta keys que
        todavía no existen; jamás toca filas ya presentes."""
        now = _ts_to_iso(_utc_now())
        for regime_state, thresholds in REGIME_THRESHOLDS.items():
            for field, value in thresholds.items():
                key = f"risk.regime.{regime_state}.{field}"
                exists = conn.execute(
                    "SELECT 1 FROM config_history WHERE key = ?", (key,)
                ).fetchone()
                if exists is None:
                    conn.execute(
                        """
                        INSERT INTO config_history
                            (key, value, version, changed_by, reason, valid_from)
                        VALUES (?, ?, 1, ?, ?, ?)
                        """,
                        (key, json.dumps(value), INITIAL_ESTIMATE, _SEED_REASON, now),
                    )

    def set(
        self,
        key: str,
        value: Any,
        changed_by: str,
        reason: str,
        valid_from: Optional[datetime] = None,
    ) -> None:
        """Inserta una nueva versión de 'key'. NUNCA hace UPDATE: solo INSERT
        (append-only, igual que config_history de indicAgent). La versión es
        MAX(version)+1; valid_from por defecto = ahora (UTC)."""
        ts = _ts_to_iso(valid_from) if valid_from is not None else _ts_to_iso(_utc_now())
        with sqlite3.connect(self.db_path) as conn:
            max_version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM config_history WHERE key = ?",
                (key,),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO config_history
                    (key, value, version, changed_by, reason, valid_from)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, json.dumps(value), max_version + 1, changed_by, reason, ts),
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Valor vigente HOY (última versión)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM config_history WHERE key = ? ORDER BY version DESC LIMIT 1",
                (key,),
            ).fetchone()
        return default if row is None else json.loads(row[0])

    def get_at(self, key: str, timestamp: datetime, default: Any = None) -> Any:
        """Valor vigente en 'timestamp' — última versión con valid_from <= timestamp.

        Este es el método que usa backtest_engine para reconstruir el estado
        histórico real de un parámetro: un ajuste hecho HOY no puede contaminar
        un backtest de fechas pasadas."""
        ts = _ts_to_iso(timestamp)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT value FROM config_history
                WHERE key = ? AND valid_from <= ?
                ORDER BY version DESC LIMIT 1
                """,
                (key, ts),
            ).fetchone()
        return default if row is None else json.loads(row[0])
