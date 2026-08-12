"""Logging estructurado JSON para Fortress Core.

Basado en las mejores prácticas del template de producción FastAPI más
premiado en GitHub (zhanymkanov/fastapi_production_template).
"""
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Formatea logs como JSON estructurado para mejor observabilidad."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Añadir request_id si existe en el contexto
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Añadir campos extra del record
        for key, value in record.__dict__.items():
            if key not in ("name", "msg", "args", "levelname", "levelno",
                           "pathname", "filename", "module", "exc_info",
                           "exc_text", "stack_info", "lineno", "funcName",
                           "created", "msecs", "relativeCreated", "thread",
                           "threadName", "processName", "process", "message",
                           "taskName", "request_id"):
                log_entry[key] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configura logging estructurado JSON para toda la aplicación."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Limpiar handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Handler de consola con formato JSON
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)

    # Reducir verbosidad de librerías externas
    for lib in ("uvicorn", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_request_id() -> str:
    """Genera un request_id único para trazabilidad."""
    return str(uuid.uuid4())


logger = logging.getLogger("fortress")
