"""Пакетное обогащение лидов myhome.ge; JSON-отчёт в stdout."""

from __future__ import annotations

import json
import logging
import sys

from sqlalchemy import text

from config.settings import Settings
from parsers.myhome import MyHomeParser
from parsers.myhome_enricher import MyHomeEnricher
from repositories.postgres_lead_repository import (
    PostgresLeadRepository,
    PostgresSessionFactory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("run_myhome_enricher")


def _ping_db(sessions: PostgresSessionFactory) -> None:
    with sessions.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def main() -> int:
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    leads = repo.list_pending_enrichment(MyHomeParser.SOURCE, limit=settings.myhome_enrich_limit)

    enricher = MyHomeEnricher(repo, headless=True)
    report = enricher.enrich_leads(leads)

    print(
        json.dumps(
            {
                "enriched": report.enriched,
                "failed": report.failed,
                "errors": report.errors,
            },
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal: %s", type(exc).__name__)
        print(
            json.dumps(
                {"enriched": 0, "failed": 0, "errors": [type(exc).__name__]},
                ensure_ascii=False,
            ),
        )
        sys.exit(1)
