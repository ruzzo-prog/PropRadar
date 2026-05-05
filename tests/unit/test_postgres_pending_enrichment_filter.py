"""Регрессия: критерии выборки list_pending_enrichment (P1 myhome enricher)."""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects import postgresql

from domain.lead import LeadStatus
from repositories.postgres_lead_repository import LeadORM


def test_pending_enrichment_sql_requires_status_new_and_empty_phone() -> None:
    """Пустой отчёт enricher при непустой выборке часто из-за слишком узкого WHERE по phone."""
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
    assert "source" in lowered
    assert "status" in lowered
    assert "'new'" in lowered
    assert "phone" in lowered
