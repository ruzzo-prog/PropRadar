"""Аутентификация HTTP API (PROPRADAR_API_KEY)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from config.settings import Settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_settings() -> Settings:
    """Новый экземпляр настроек (удобно для тестов с monkeypatch env)."""
    return Settings()


def _is_development(settings: Settings) -> bool:
    return settings.app_env.lower() in ("development", "dev", "local")


def verify_propradar_api_key(
    x_api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """В development ключ опционален; в production — обязателен и сверяется с PROPRADAR_API_KEY."""
    if _is_development(settings):
        if (
            settings.propradar_api_key
            and x_api_key is not None
            and x_api_key != settings.propradar_api_key
        ):
            raise HTTPException(status_code=403, detail="Invalid API key")
        return
    server_key = (settings.propradar_api_key or "").strip()
    if not server_key:
        raise HTTPException(status_code=403, detail="PROPRADAR_API_KEY not configured")
    if not x_api_key or x_api_key != server_key:
        raise HTTPException(status_code=403, detail="Missing or invalid API key")
