from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from domain.lead import Lead

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
    def list_pending_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        """Кандидаты на обогащение: status=new, phone пустой (NULL или ''), source совпадает."""

    @abstractmethod
    def update_enriched_fields(self, entity: Lead) -> Lead:
        """Обновить поля деталей/телефона по id. Требуется entity.id."""
