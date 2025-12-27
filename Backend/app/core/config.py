from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/convo",
        alias="DATABASE_URL",
    )
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    hold_ttl_minutes: int = Field(default=5, alias="HOLD_TTL_MINUTES")
    working_hours_start: str = Field(default="09:00", alias="WORKING_HOURS_START")
    working_hours_end: str = Field(default="17:00", alias="WORKING_HOURS_END")
    default_shop_name: str = Field(default="Bishops Tempe", alias="DEFAULT_SHOP_NAME")

    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
