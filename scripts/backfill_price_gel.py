"""Однократный backfill поля ``price_gel`` для лидов myhome (``status=new``, ``price_gel IS NULL``).

Для каждой записи вызывается тот же путь, что и в enricher: GET ``/v1/statements/{external_id}``,
``statement_to_lead_updates`` (в т.ч. ``price.1.price_total``) → ``update_enriched_fields``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

import httpx
from sqlalchemy import and_, select
from sqlalchemy import text as sql_text

from config.settings import Settings
from domain.lead import LeadStatus
from parsers.adapters.myhome.enricher import MyHomeEnricher
from parsers.myhome import MyHomeParser
from repositories.postgres_lead_repository import (
    LeadORM,
    PostgresLeadRepository,
    PostgresSessionFactory,
    _to_domain,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("backfill_price_gel")


def _ping_db(sessions: PostgresSessionFactory) -> None:
    with sessions.engine.connect() as conn:
        conn.execute(sql_text("SELECT 1"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill price_gel для myhome: только new и price_gel IS NULL.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Максимум записей за запуск (1–500).",
    )
    args = parser.parse_args()
    lim = max(1, min(args.limit, 500))

    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    src = MyHomeParser.SOURCE

    with sessions.factory() as session:
        stmt = (
            select(LeadORM)
            .where(
                and_(
                    LeadORM.source == src,
                    LeadORM.status == LeadStatus.NEW.value,
                    LeadORM.price_gel.is_(None),
                ),
            )
            .order_by(LeadORM.created_at.asc())
            .limit(lim)
        )
        rows = session.scalars(stmt).all()
        leads = [_to_domain(r) for r in rows]

    logger.info("backfill_price_gel: batch_size=%s limit=%s", len(leads), lim)

    with httpx.Client() as http_client:
        enricher = MyHomeEnricher(
            repo,
            base_url=str(settings.myhome_api_base_url),
            client=http_client,
        )
        report = enricher.enrich_leads(leads)

    summary = {
        "candidates": len(leads),
        "enriched": report.enriched,
        "failed": report.failed,
        "errors": report.errors,
    }
    print(json.dumps(summary, ensure_ascii=False))
    logger.info(
        "backfill_price_gel: summary enriched=%s failed=%s",
        report.enriched,
        report.failed,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal: %s", type(exc).__name__)
        print(json.dumps({"fatal": type(exc).__name__}, ensure_ascii=False))
        sys.exit(1)
