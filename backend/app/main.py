import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import backtest, decision, governance, live, market, opportunities, predict, risk, system
from app.config import settings
from app.models.database import engine, init_db
from app.utils.logging import get_request_id, logger, setup_logging

# Configurar logging estructurado JSON
setup_logging("INFO" if settings.ENVIRONMENT == "development" else "WARNING")

app = FastAPI(
    title="Fortress Core — Deterministic MVP",
    description="Sistema de trading cuantitativo con gestión de riesgo adaptativa",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.include_router(risk.router)
app.include_router(system.router)
app.include_router(backtest.router)
app.include_router(market.router)
app.include_router(live.router)
app.include_router(predict.router)
app.include_router(governance.router)
app.include_router(opportunities.router)
app.include_router(decision.router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Añade request_id a cada petición para trazabilidad."""
    request_id = request.headers.get("X-Request-ID", get_request_id())
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time_ms": round(process_time * 1000, 2),
        },
    )
    return response


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Fortress Core backend started", extra={"environment": settings.ENVIRONMENT})


@app.get("/health")
async def health():
    """Health check que verifica la conexión a la base de datos."""
    db_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"
        logger.error("health_check_db_failed", extra={"error": str(e)})

    from app.core.advanced_agents import NvidiaNIMClient
    ai_layer = "enabled" if NvidiaNIMClient().is_available() else "disabled"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "ai_layer": ai_layer,
        "database": db_status,
        "environment": settings.ENVIRONMENT,
    }
