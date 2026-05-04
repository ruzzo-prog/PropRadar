from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import String, func, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import BigInteger, DateTime

from domain.lead import Lead, LeadStatus
from repositories.base import LeadRepository


class Base(DeclarativeBase):
    pass


class LeadORM(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    source_listing_uuid: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    price_total_usd: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    price_m2_usd: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _to_domain(row: LeadORM) -> Lead:
    return Lead(
        id=row.id,
        source=row.source,
        external_id=row.external_id,
        status=LeadStatus(row.status),
        score=row.score,
        created_at=row.created_at,
        updated_at=row.updated_at,
        source_listing_uuid=row.source_listing_uuid,
        price_total_usd=row.price_total_usd,
        price_m2_usd=row.price_m2_usd,
        published_at=row.published_at,
    )


@dataclass
class PostgresSessionFactory:
    engine: Engine
    factory: sessionmaker[Session]

    @classmethod
    def from_database_url(cls, url: str) -> PostgresSessionFactory:
        from sqlalchemy import create_engine

        eng = create_engine(url, pool_pre_ping=True)
        factory = sessionmaker(bind=eng, expire_on_commit=False)
        return cls(engine=eng, factory=factory)


class PostgresLeadRepository(LeadRepository):
    def __init__(self, sessions: PostgresSessionFactory) -> None:
        self._sessions = sessions

    def get_by_id(self, entity_id: UUID) -> Lead | None:
        with self._sessions.factory() as session:
            row = session.get(LeadORM, entity_id)
            return _to_domain(row) if row else None

    def get_by_source_and_external_id(self, source: str, external_id: str) -> Lead | None:
        with self._sessions.factory() as session:
            stmt = select(LeadORM).where(
                LeadORM.source == source,
                LeadORM.external_id == external_id,
            )
            row = session.scalars(stmt).first()
            return _to_domain(row) if row else None

    def save(self, entity: Lead) -> Lead:
        if entity.id is not None:
            msg = "PostgresLeadRepository.save ожидает новый Lead без id"
            raise ValueError(msg)
        row = LeadORM(
            source=entity.source,
            external_id=entity.external_id,
            status=entity.status.value,
            score=entity.score,
            source_listing_uuid=entity.source_listing_uuid,
            price_total_usd=entity.price_total_usd,
            price_m2_usd=entity.price_m2_usd,
            published_at=entity.published_at,
        )
        with self._sessions.factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_domain(row)
