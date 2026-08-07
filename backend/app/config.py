from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SQLite por defecto para desarrollo local sin Docker
    DATABASE_URL: str = "sqlite:///./fortress.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "change-me-in-production"
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    ABSOLUTE_CEILING: float = 0.12
    RISK_PER_TRADE: float = 0.015
    MAX_POSITION_PCT: float = 0.10
    INITIAL_CAPITAL: float = 25000.0
    TARGET_VOLATILITY: float = 0.10
    VIOLATION_WINDOW_DAYS: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()