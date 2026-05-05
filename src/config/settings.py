from __future__ import annotations

from pathlib import Path

from pydantic import Field, HttpUrl, PostgresDsn
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
    myhome_api_base_url: HttpUrl = Field(
        default="https://api-statements.tnet.ge",
        validation_alias="MYHOME_API_BASE_URL",
    )
    myhome_email: str | None = Field(default=None, validation_alias="MYHOME_EMAIL")
    myhome_password: str | None = Field(default=None, validation_alias="MYHOME_PASSWORD")
    myhome_session_path: Path = Field(
        default=Path("scripts/myhome_session.json"),
        validation_alias="MYHOME_SESSION_PATH",
    )
    myhome_enrich_limit: int = Field(
        default=50,
        ge=1,
        le=500,
        validation_alias="MYHOME_ENRICH_LIMIT",
    )
    myhome_pdf_output_dir: Path = Field(
        default=Path("data/myhome_pdf"),
        validation_alias="MYHOME_PDF_OUTPUT_DIR",
    )
    myhome_pdf_public_base_url: str | None = Field(
        default=None,
        validation_alias="MYHOME_PDF_PUBLIC_BASE_URL",
    )
