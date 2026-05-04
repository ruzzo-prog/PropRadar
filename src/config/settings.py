from __future__ import annotations

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения из окружения. Значения секретов никогда не логировать."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    database_url: PostgresDsn = Field(
        default="postgresql://leads:changeme@localhost:5433/leads",
        validation_alias="DATABASE_URL",
    )
