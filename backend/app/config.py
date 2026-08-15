from pydantic import model_validator
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

    # Costo de transacción por lado usado en los backtests de costos. Valor ASUMIDO
    # (0.10% comisión + 0.05% slippage), pendiente de medición real por M4
    # (app/core/execution_costs.py). Cuando exista medición, este es el único lugar
    # a actualizar — lo consumen barrier_labeling (ret_net) y los trials de costos.
    # NO cambiarlo a mano a un valor "realista": la medición manda.
    COST_PER_SIDE: float = 0.0015

    # Alpaca PAPER TRADING — medición de costos reales (M4, app/core/execution_costs.py).
    # ÚNICO propósito: medir slippage/fill reales contra el precio de decisión. Jamás
    # una orden en cuenta live. Credenciales solo acá vía .env / variables de entorno,
    # NUNCA en código ni en el chat. Vacías = el cliente de medición no se instancia
    # (construye, no bloquea: la medición es la única pieza que las necesita).
    ALPACA_PAPER_API_KEY: str = ""
    ALPACA_PAPER_SECRET_KEY: str = ""
    ALPACA_PAPER_BASE_URL: str = "https://paper-api.alpaca.markets"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @model_validator(mode="after")
    def _require_secure_secret_key(self):
        if self.ENVIRONMENT != "development" and (
            not self.SECRET_KEY or self.SECRET_KEY == "change-me-in-production"
        ):
            raise ValueError(
                "SECRET_KEY debe configurarse vía .env — el default "
                "'change-me-in-production' solo es válido en development."
            )
        return self


settings = Settings()
