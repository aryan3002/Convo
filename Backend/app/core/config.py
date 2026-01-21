from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:55432/convo",
        alias="DATABASE_URL",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    allowed_origins: str = Field(default="http://localhost:3000", alias="ALLOWED_ORIGINS")
    hold_ttl_minutes: int = Field(default=5, alias="HOLD_TTL_MINUTES")
    working_hours_start: str = Field(default="09:00", alias="WORKING_HOURS_START")
    working_hours_end: str = Field(default="17:00", alias="WORKING_HOURS_END")
    # Default Monday-Saturday (0 = Monday, 6 = Sunday)
    working_days: str = Field(default="0,1,2,3,4,5", alias="WORKING_DAYS")
    default_shop_name: str = Field(default="Bishops Tempe", alias="DEFAULT_SHOP_NAME")
    chat_timezone: str = Field(default="America/Phoenix", alias="CHAT_TIMEZONE")
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    resend_from: str | None = Field(default=None, alias="RESEND_FROM")
    public_api_base: str = Field(default="http://localhost:8000", alias="PUBLIC_API_BASE")
    cloudinary_cloud_name: str | None = Field(default=None, alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_upload_preset: str | None = Field(default=None, alias="CLOUDINARY_UPLOAD_PRESET")
    cloudinary_api_key: str | None = Field(default=None, alias="CLOUDINARY_API_KEY")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, alias="TWILIO_FROM_NUMBER")
    twilio_verify_signature: bool = Field(default=False, alias="TWILIO_VERIFY_SIGNATURE")
    # ChatGPT Custom GPT Public Booking API Key
    public_booking_api_key: str = Field(
        default="convo-public-booking-key-2024",
        alias="PUBLIC_BOOKING_API_KEY",
        description="API key for ChatGPT Custom GPT public booking endpoints"
    )

    model_config = SettingsConfigDict(env_file=(".env", "Backend/.env", "backend/.env"), extra="ignore")

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def working_days_list(self) -> List[int]:
        raw_days = [int(day) for day in self.working_days.split(",") if day.strip()]
        # If user supplied 1-7 (Mon-Sun), normalize to Python weekday() 0-6 (Mon-Sun)
        if raw_days and min(raw_days) >= 1 and max(raw_days) <= 7 and 0 not in raw_days:
            return sorted({(day - 1) % 7 for day in raw_days})
        return raw_days


@lru_cache
def get_settings() -> Settings:
    return Settings()
