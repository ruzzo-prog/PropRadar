from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, HttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения из окружения. Значения секретов никогда не логировать."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    propradar_api_key: str | None = Field(
        default=None,
        validation_alias="PROPRADAR_API_KEY",
        description=(
            "Ключ для HTTP API (/api/myhome/*). В production обязателен; "
            "без заголовка X-API-Key — 403."
        ),
    )
    propradar_repo_root: Path | None = Field(
        default=None,
        validation_alias="PROPRADAR_REPO_ROOT",
        description=(
            "Корень репозитория для subprocess к scripts/. "
            "По умолчанию вычисляется от расположения api."
        ),
    )
    myhome_cli_timeout_seconds: int = Field(
        default=3600,
        ge=30,
        le=86_400,
        validation_alias="MYHOME_CLI_TIMEOUT_SECONDS",
        description="Таймаут subprocess для CLI myhome (ingest может быть долгим).",
    )
    database_url: PostgresDsn = Field(
        default="postgresql://leads:changeme@localhost:5433/leads",
        validation_alias="DATABASE_URL",
    )
    myhome_api_base_url: HttpUrl = Field(
        default="https://api-statements.tnet.ge",
        validation_alias="MYHOME_API_BASE_URL",
    )
    myhome_ids_snapshot_path: Path = Field(
        default=Path("/data/myhome_ids_snapshot.json"),
        validation_alias="MYHOME_IDS_SNAPSHOT_PATH",
    )
    myhome_ids_snapshot_lock_path: Path = Field(
        default=Path("/data/.ids_snapshot.lock"),
        validation_alias="MYHOME_IDS_SNAPSHOT_LOCK_PATH",
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
    playwright_proxy_server: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PLAYWRIGHT_PROXY_SERVER"),
    )
    playwright_proxy_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PLAYWRIGHT_PROXY_USER"),
    )
    playwright_proxy_pass: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PLAYWRIGHT_PROXY_PASS"),
    )
    twocaptcha_api_key: str | None = Field(
        default=None,
        validation_alias="TWOCAPTCHA_API_KEY",
        description="API-ключ 2captcha для reCAPTCHA v3 (HTTP phone enricher).",
    )
    myhome_recaptcha_site_key: str = Field(
        default="6LeziPEpAAAAAHuR9vWBVCrfklSbWt8zixM4jAbM",
        validation_alias="MYHOME_RECAPTCHA_SITE_KEY",
    )
    myhome_phone_http_workers: int = Field(
        default=5,
        ge=1,
        le=10,
        validation_alias="MYHOME_PHONE_HTTP_WORKERS",
    )
    myhome_phone_http_enabled: bool = Field(
        default=True,
        validation_alias="MYHOME_PHONE_HTTP_ENABLED",
    )
    myhome_phone_playwright_fallback: bool = Field(
        default=False,
        validation_alias="MYHOME_PHONE_PLAYWRIGHT_FALLBACK",
        description="CLI: после HTTP-фазы запустить Playwright для оставшихся без phone.",
    )
