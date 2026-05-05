from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from domain.lead import Lead, LeadStatus

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Базовый репозиторий (доступ к персистентности). Конкретные реализации — отдельные классы."""

    @abstractmethod
    def get_by_id(self, entity_id: UUID) -> T | None: ...

    @abstractmethod
    def save(self, entity: T) -> T: ...


class LeadRepository(Repository[Lead], ABC):
    """Порт хранения лидов."""

    @abstractmethod
    def get_by_source_and_external_id(self, source: str, external_id: str) -> Lead | None: ...

    @abstractmethod
    def list_pending_detail_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        """Очередь детализации (API): status=new, source, address IS NULL."""

    @abstractmethod
    def list_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        """Очередь телефона (Playwright): status=new, source, phone пустой (NULL или '')."""

    @abstractmethod
    def list_pending_pdf_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        """PDF карточки: status=new, source, pdf_url IS NULL, address уже заполнен."""

    @abstractmethod
    def update_enriched_fields(self, entity: Lead) -> Lead:
        """Обновить поля деталей/телефона по id. Требуется entity.id."""

    @abstractmethod
    def list_external_ids_by_source_and_status(
        self,
        source: str,
        status: LeadStatus,
    ) -> list[str]:
        """Список external_id для источника и статуса."""

    @abstractmethod
    def mark_leads_by_external_ids(
        self,
        source: str,
        external_ids: list[str],
        *,
        status: LeadStatus,
        status_reason: str | None = None,
    ) -> int:
        """Перевести лиды в статус (только из status=new). Возвращает число обновлённых строк."""
