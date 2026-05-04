from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, String, and_, func, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import BigInteger, Boolean, DateTime, Numeric, Text

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
    phone: Mapped[str | None] = mapped_column(Text(), nullable=True)
    address: Mapped[str | None] = mapped_column(Text(), nullable=True)
    district: Mapped[str | None] = mapped_column(Text(), nullable=True)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))


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
        phone=row.phone,
        address=row.address,
        district=row.district,
        area_m2=row.area_m2,
        rooms=row.rooms,
        floor=row.floor,
        description=row.description,
        is_owner=row.is_owner,
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
            phone=entity.phone,
            address=entity.address,
            district=entity.district,
            area_m2=entity.area_m2,
            rooms=entity.rooms,
            floor=entity.floor,
            description=entity.description,
            is_owner=entity.is_owner,
        )
        with self._sessions.factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_domain(row)

    def list_pending_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        lim = max(1, min(limit, 500))
        with self._sessions.factory() as session:
            stmt = (
                select(LeadORM)
                .where(
                    and_(
                        LeadORM.source == source,
                        LeadORM.status == LeadStatus.NEW.value,
                        LeadORM.phone.is_(None),
                    ),
                )
                .order_by(LeadORM.created_at.asc())
                .limit(lim)
            )
            rows = session.scalars(stmt).all()
            return [_to_domain(r) for r in rows]

    def update_enriched_fields(self, entity: Lead) -> Lead:
        if entity.id is None:
            msg = "update_enriched_fields ожидает Lead с id"
            raise ValueError(msg)
        with self._sessions.factory() as session:
            row = session.get(LeadORM, entity.id)
            if row is None:
                msg = "лид не найден"
                raise ValueError(msg)
            row.phone = entity.phone
            row.address = entity.address
            row.district = entity.district
            row.area_m2 = entity.area_m2
            row.rooms = entity.rooms
            row.floor = entity.floor
            row.description = entity.description
            row.is_owner = entity.is_owner
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _to_domain(row)
