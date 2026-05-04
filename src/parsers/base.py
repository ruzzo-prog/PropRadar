from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.lead import Lead


class BaseParser(ABC):
    """Контракт парсера источника объявлений. Реализации — в отдельных модулях."""

    @abstractmethod
    async def fetch_raw_batch(self) -> list[dict[str, Any]]:
        """Загрузить сырой пакет записей с источника (HTTP/Playwright и т.д.)."""

    @abstractmethod
    async def parse_lead(self, raw: dict[str, Any]) -> Lead | None:
        """Преобразовать одну сырую запись в доменный Lead или отбросить (None)."""
