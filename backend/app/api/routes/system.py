from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
async def system_status():
    return {
        "risk_manager_active": True,
        "absolute_ceiling": settings.ABSOLUTE_CEILING,
        "risk_per_trade": settings.RISK_PER_TRADE,
        "violation_window_days": settings.VIOLATION_WINDOW_DAYS,
        "ai_agents_enabled": False,
        "phase": "1 - Fortress Core (deterministic only)",
    }