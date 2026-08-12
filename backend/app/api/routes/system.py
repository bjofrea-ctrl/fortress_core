from fastapi import APIRouter

from app.config import settings
from app.core.advanced_agents import NvidiaNIMClient

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
async def system_status():
    ai_enabled = NvidiaNIMClient().is_available()
    return {
        "risk_manager_active": True,
        "absolute_ceiling": settings.ABSOLUTE_CEILING,
        "risk_per_trade": settings.RISK_PER_TRADE,
        "violation_window_days": settings.VIOLATION_WINDOW_DAYS,
        "ai_agents_enabled": ai_enabled,
        "phase": "4 - predictive engine + triad + governance" if ai_enabled else "1-3 - deterministic + predictive (sin LLM configurado)",
    }
