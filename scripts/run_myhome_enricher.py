"""Пакетное обогащение лидов myhome.ge; JSON-отчёт в stdout."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from sqlalchemy import text

from config.settings import Settings
from parsers.exceptions import SessionExpiredError
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


def _session_path(settings: Settings) -> Path:
    p = settings.myhome_session_path
    return p if p.is_absolute() else (Path.cwd() / p).resolve()


def main() -> int:
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    leads = repo.list_pending_enrichment(MyHomeParser.SOURCE, limit=settings.myhome_enrich_limit)
    session_file = _session_path(settings)

    enricher = MyHomeEnricher(
        repo,
        session_storage_path=session_file,
        headless=True,
    )
    try:
        report = enricher.enrich_leads(leads)
    except SessionExpiredError:
        payload = {
            "enriched": 0,
            "failed": len(leads),
            "errors": ["session_expired"],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1

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
