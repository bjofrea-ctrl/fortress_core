from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SQLite por defecto para desarrollo local sin Docker
    DATABASE_URL: str = "sqlite:///./fortress.db"
    SECRET_KEY: str = "change-me-in-production"
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Antes NvidiaNIMClient leía estas variables directo de os.environ, que
    # nunca se populaba (nada llama a load_dotenv(), y docker-compose.yml no
    # las pasa al contenedor) — la key configurada en .env nunca llegaba al
    # proceso real. Unificado bajo Settings, que sí lee .env correctamente.
    NVIDIA_NIM_API_KEY: str = ""
    NVIDIA_NIM_MODEL: str = "meta/llama-3.1-8b-instruct"
    NVIDIA_NIM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    # Fundamentales reales (free tier: https://finnhub.io/register) — sin
    # esto, get_fundamentals() sigue usando el sample hardcodeado de 6 tickers.
    FINNHUB_API_KEY: str = ""

    # Notificaciones diarias (Pieza 4): aviso de oportunidades 16:30 ET.
    # Vacíos = canal desactivado; el notifier salta el canal sin fallar.
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_TO: str = ""

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