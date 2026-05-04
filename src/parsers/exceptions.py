"""Исключения парсеров (без зависимостей от Playwright/HTTP)."""

from __future__ import annotations

_SESSION_MSG = "Запустите scripts/myhome_login.py"


class SessionExpiredError(Exception):
    """Сессия myhome.ge недействительна — нужен повторный логин и storage_state."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or _SESSION_MSG)
