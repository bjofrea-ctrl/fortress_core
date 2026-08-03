from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.database import SessionLocal, RiskEvent, PortfolioSnapshot
from app.config import settings
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/risk", tags=["risk"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/monitor")
async def risk_monitor(db: Session = Depends(get_db)):
    latest = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).first()
    if not latest:
        return {"status": "no_data", "absolute_ceiling": settings.ABSOLUTE_CEILING}

    cutoff = datetime.utcnow() - timedelta(days=settings.VIOLATION_WINDOW_DAYS)
    violations_60d = db.query(RiskEvent).filter(
        RiskEvent.is_violation == True,
        RiskEvent.date >= cutoff
    ).count()

    return {
        "current_equity": latest.equity,
        "current_drawdown_pct": latest.drawdown_pct,
        "absolute_ceiling": settings.ABSOLUTE_CEILING,
        "regime_state": latest.regime_state,
        "num_positions": latest.num_positions,
        "violations_60d": violations_60d,
    }