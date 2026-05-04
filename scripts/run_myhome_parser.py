"""Точка входа для n8n: один прогон MyHomeParser, JSON-отчёт в stdout."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import httpx

from config.settings import Settings
from parsers.myhome import MyHomeParser
from repositories.postgres_lead_repository import (
    PostgresLeadRepository,
    PostgresSessionFactory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("run_myhome_parser")


def _ping_db(sessions: PostgresSessionFactory) -> None:
    from sqlalchemy import text

    with sessions.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


async def _async_main() -> None:
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    async with httpx.AsyncClient() as client:
        parser = MyHomeParser(client, repo, base_url=str(settings.myhome_api_base_url))
        report = await parser.run()
    print(
        json.dumps(
            {"parsed": report.parsed, "new": report.new, "errors": report.errors},
            ensure_ascii=False,
        ),
    )


def main() -> None:
    try:
        asyncio.run(_async_main())
    except httpx.HTTPError:
        print(
            json.dumps({"parsed": 0, "new": 0, "errors": ["http_error"]}, ensure_ascii=False),
        )
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 — верхний уровень CLI
        logger.error("Fatal error: %s", type(exc).__name__)
        print(
            json.dumps({"parsed": 0, "new": 0, "errors": [type(exc).__name__]}, ensure_ascii=False),
        )
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
