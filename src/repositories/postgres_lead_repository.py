from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, String, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
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
    status_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    price_gel: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    price_usd: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    price_m2_usd: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phone: Mapped[str | None] = mapped_column(Text(), nullable=True)
    phone_retries: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        server_default=text("0"),
    )
    address: Mapped[str | None] = mapped_column(Text(), nullable=True)
    address_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    district: Mapped[str | None] = mapped_column(Text(), nullable=True)
    district_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    description_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    geo_lat: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    geo_lng: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    listing_views: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    myhome_statement_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text(), nullable=True)


def _to_domain(row: LeadORM) -> Lead:
    return Lead(
        id=row.id,
        source=row.source,
        external_id=row.external_id,
        status=LeadStatus(row.status),
        status_reason=row.status_reason,
        score=row.score,
        created_at=row.created_at,
        updated_at=row.updated_at,
        source_listing_uuid=row.source_listing_uuid,
        price_gel=row.price_gel,
        price_usd=row.price_usd,
        price_m2_usd=row.price_m2_usd,
        published_at=row.published_at,
        phone=row.phone,
        phone_retries=row.phone_retries,
        address=row.address,
        address_lang=row.address_lang,
        district=row.district,
        district_lang=row.district_lang,
        area_m2=row.area_m2,
        rooms=row.rooms,
        floor=row.floor,
        description=row.description,
        description_lang=row.description_lang,
        is_owner=row.is_owner,
        geo_lat=row.geo_lat,
        geo_lng=row.geo_lng,
        listing_views=row.listing_views,
        myhome_statement_json=(
            dict(row.myhome_statement_json) if row.myhome_statement_json else None
        ),
        pdf_url=row.pdf_url,
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
            status_reason=entity.status_reason,
            score=entity.score,
            source_listing_uuid=entity.source_listing_uuid,
            price_gel=entity.price_gel,
            price_usd=entity.price_usd,
            price_m2_usd=entity.price_m2_usd,
            published_at=entity.published_at,
            phone=entity.phone,
            phone_retries=entity.phone_retries,
            address=entity.address,
            address_lang=entity.address_lang,
            district=entity.district,
            district_lang=entity.district_lang,
            area_m2=entity.area_m2,
            rooms=entity.rooms,
            floor=entity.floor,
            description=entity.description,
            description_lang=entity.description_lang,
            is_owner=entity.is_owner,
            geo_lat=entity.geo_lat,
            geo_lng=entity.geo_lng,
            listing_views=entity.listing_views,
            myhome_statement_json=entity.myhome_statement_json,
            pdf_url=entity.pdf_url,
        )
        with self._sessions.factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_domain(row)

    def list_pending_detail_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        lim = max(1, min(limit, 500))
        with self._sessions.factory() as session:
            stmt = (
                select(LeadORM)
                .where(
                    and_(
                        LeadORM.source == source,
                        LeadORM.status == LeadStatus.NEW.value,
                        or_(
                            LeadORM.address.is_(None),
                            LeadORM.price_gel.is_(None),
                        ),
                    ),
                )
                .order_by(LeadORM.created_at.asc())
                .limit(lim)
            )
            rows = session.scalars(stmt).all()
            return [_to_domain(r) for r in rows]

    @staticmethod
    def _phone_queue_filters(source: str) -> tuple:
        return (
            LeadORM.source == source,
            LeadORM.status == LeadStatus.NEW.value,
            or_(
                LeadORM.phone.is_(None),
                LeadORM.phone == "",
            ),
            LeadORM.phone_retries < 3,
        )

    def list_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        lim = max(1, min(limit, 500))
        with self._sessions.factory() as session:
            stmt = (
                select(LeadORM)
                .where(and_(*self._phone_queue_filters(source)))
                .order_by(LeadORM.created_at.asc())
                .limit(lim)
            )
            rows = session.scalars(stmt).all()
            return [_to_domain(r) for r in rows]

    def claim_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        lim = max(1, min(limit, 500))
        with self._sessions.factory() as session:
            stmt = (
                select(LeadORM)
                .where(and_(*self._phone_queue_filters(source)))
                .order_by(LeadORM.created_at.asc())
                .limit(lim)
                .with_for_update(skip_locked=True)
            )
            rows = session.scalars(stmt).all()
            return [_to_domain(r) for r in rows]

    def increment_phone_retry(self, lead_id: UUID) -> int:
        with self._sessions.factory() as session:
            row = session.get(LeadORM, lead_id)
            if row is None:
                msg = "лид не найден"
                raise ValueError(msg)
            row.phone_retries = int(row.phone_retries or 0) + 1
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return int(row.phone_retries)

    def mark_phone_enrich_exhausted(self, lead_id: UUID) -> None:
        with self._sessions.factory() as session:
            row = session.get(LeadORM, lead_id)
            if row is None:
                msg = "лид не найден"
                raise ValueError(msg)
            row.status_reason = "phone_enrich_failed"
            row.updated_at = datetime.now(UTC)
            session.commit()

    def list_pending_pdf_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        lim = max(1, min(limit, 500))
        with self._sessions.factory() as session:
            stmt = (
                select(LeadORM)
                .where(
                    and_(
                        LeadORM.source == source,
                        LeadORM.status == LeadStatus.NEW.value,
                        LeadORM.address.isnot(None),
                        LeadORM.address != "",
                        or_(
                            LeadORM.pdf_url.is_(None),
                            LeadORM.pdf_url == "",
                        ),
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
            if entity.phone is not None:
                row.phone = entity.phone
            if entity.price_gel is not None:
                row.price_gel = entity.price_gel
            if entity.price_usd is not None:
                row.price_usd = entity.price_usd
            if entity.price_m2_usd is not None:
                row.price_m2_usd = entity.price_m2_usd
            if entity.source_listing_uuid is not None:
                row.source_listing_uuid = entity.source_listing_uuid
            if entity.address is not None:
                row.address = entity.address
            if entity.address_lang is not None:
                row.address_lang = entity.address_lang
            if entity.district is not None:
                row.district = entity.district
            if entity.district_lang is not None:
                row.district_lang = entity.district_lang
            if entity.area_m2 is not None:
                row.area_m2 = entity.area_m2
            if entity.rooms is not None:
                row.rooms = entity.rooms
            if entity.floor is not None:
                row.floor = entity.floor
            if entity.description is not None:
                row.description = entity.description
            if entity.description_lang is not None:
                row.description_lang = entity.description_lang
            if entity.published_at is not None:
                row.published_at = entity.published_at
            if entity.is_owner is True:
                row.is_owner = True
            if entity.geo_lat is not None:
                row.geo_lat = entity.geo_lat
            if entity.geo_lng is not None:
                row.geo_lng = entity.geo_lng
            if entity.listing_views is not None:
                row.listing_views = entity.listing_views
            if entity.myhome_statement_json is not None:
                row.myhome_statement_json = entity.myhome_statement_json
            if entity.pdf_url is not None:
                row.pdf_url = entity.pdf_url
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _to_domain(row)

    def list_external_ids_by_source_and_status(
        self,
        source: str,
        status: LeadStatus,
    ) -> list[str]:
        with self._sessions.factory() as session:
            stmt = select(LeadORM.external_id).where(
                LeadORM.source == source,
                LeadORM.status == status.value,
            )
            return list(session.scalars(stmt).all())

    def mark_leads_by_external_ids(
        self,
        source: str,
        external_ids: list[str],
        *,
        status: LeadStatus,
        status_reason: str | None = None,
    ) -> int:
        if not external_ids:
            return 0
        with self._sessions.factory() as session:
            stmt = (
                update(LeadORM)
                .where(
                    LeadORM.source == source,
                    LeadORM.external_id.in_(external_ids),
                    LeadORM.status == LeadStatus.NEW.value,
                )
                .values(
                    status=status.value,
                    status_reason=status_reason,
                    updated_at=datetime.now(UTC),
                )
            )
            result = session.execute(stmt)
            session.commit()
            return int(result.rowcount or 0)
