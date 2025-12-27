from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:55432/convo",
        alias="DATABASE_URL",
    )
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    hold_ttl_minutes: int = Field(default=5, alias="HOLD_TTL_MINUTES")
    working_hours_start: str = Field(default="09:00", alias="WORKING_HOURS_START")
    working_hours_end: str = Field(default="17:00", alias="WORKING_HOURS_END")
    working_days: str = Field(default="1,2,3,4,5,6", alias="WORKING_DAYS")
    default_shop_name: str = Field(default="Bishops Tempe", alias="DEFAULT_SHOP_NAME")
    chat_timezone: str = Field(default="America/Phoenix", alias="CHAT_TIMEZONE")
    chat_log_path: str = Field(default="Backend/chat_logs.jsonl", alias="CHAT_LOG_PATH")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    model_config = SettingsConfigDict(env_file=(".env", "Backend/.env", "backend/.env"), extra="ignore")

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def working_days_list(self) -> List[int]:
        return [int(day) for day in self.working_days.split(",") if day.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
