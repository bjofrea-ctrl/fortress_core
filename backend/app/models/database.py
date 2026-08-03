from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=settings.DATABASE_URL.startswith("postgresql"),
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class PriceData(Base):
    __tablename__ = "price_data"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), index=True)
    date = Column(DateTime, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    __table_args__ = (Index("idx_price_symbol_date", "symbol", "date"),)


class RegimeState(Base):
    __tablename__ = "regime_states"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, index=True, unique=True)
    state = Column(Integer)
    vix = Column(Float)
    confidence = Column(Float)


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), index=True)
    entry_date = Column(DateTime)
    entry_price = Column(Float)
    shares = Column(Integer)
    stop_loss = Column(Float)
    trailing_stop = Column(Float)
    status = Column(String(20), default="OPEN")
    exit_date = Column(DateTime)
    exit_price = Column(Float)
    pnl = Column(Float)
    pnl_pct = Column(Float)
    exit_reason = Column(String(50))


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, index=True)
    equity = Column(Float)
    drawdown_pct = Column(Float)
    num_positions = Column(Integer)
    exposure_pct = Column(Float)
    regime_state = Column(Integer)
    violations_count = Column(Integer)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, index=True)
    severity = Column(String(20))
    symbol = Column(String(10))
    description = Column(String(500))
    action_taken = Column(String(200))
    is_violation = Column(Boolean, default=False)


def init_db():
    Base.metadata.create_all(bind=engine)