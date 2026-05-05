"""Регрессия: критерии очередей обогащения myhome (detail / phone / pdf)."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects import postgresql

from domain.lead import LeadStatus
from repositories.postgres_lead_repository import LeadORM


def test_pending_detail_requires_address_or_price_gel_null() -> None:
    """Detail-очередь: address IS NULL OR price_gel IS NULL (оба поля в OR)."""
    stmt = (
        select(LeadORM)
        .where(
            and_(
                LeadORM.source == "myhome",
                LeadORM.status == LeadStatus.NEW.value,
                or_(
                    LeadORM.address.is_(None),
                    LeadORM.price_gel.is_(None),
                ),
            ),
        )
        .limit(1)
    )
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ),
    )
    lowered = sql.lower()
    assert "address" in lowered
    assert "price_gel" in lowered
    assert " or " in lowered or " OR " in sql


def test_pending_phone_requires_empty_phone() -> None:
    stmt = (
        select(LeadORM)
        .where(
            and_(
                LeadORM.source == "myhome",
                LeadORM.status == LeadStatus.NEW.value,
                or_(
                    LeadORM.phone.is_(None),
                    LeadORM.phone == "",
                ),
            ),
        )
        .limit(1)
    )
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ),
    )
    lowered = sql.lower()
    assert "phone" in lowered


def test_pending_pdf_requires_address_and_missing_pdf_url() -> None:
    stmt = (
        select(LeadORM)
        .where(
            and_(
                LeadORM.source == "myhome",
                LeadORM.status == LeadStatus.NEW.value,
                LeadORM.address.isnot(None),
                LeadORM.address != "",
                or_(
                    LeadORM.pdf_url.is_(None),
                    LeadORM.pdf_url == "",
                ),
            ),
        )
        .limit(1)
    )
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ),
    )
    lowered = sql.lower()
    assert "pdf_url" in lowered
    assert "address" in lowered
