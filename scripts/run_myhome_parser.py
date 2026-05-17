"""Точка входа для n8n: один прогон MyHomeParser, JSON-отчёт в stdout."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import httpx

from config.settings import Settings
from parsers.adapters.myhome.ingest_detail import ingest_new_leads_by_detail_ids
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


async def _async_main(*, ingest_ids_json: Path | None) -> None:
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    base_url = str(settings.myhome_api_base_url)
    async with httpx.AsyncClient() as client:
        if ingest_ids_json is not None:
            raw = ingest_ids_json.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                msg = "--ingest-ids-json: ожидается JSON-массив"
                raise ValueError(msg)
            ids = [str(x).strip() for x in data if x is not None]
            ids = [x for x in ids if x]
            max_concurrent = int(os.getenv("MYHOME_INGEST_CONCURRENCY", "20"))
            report = await ingest_new_leads_by_detail_ids(
                client,
                repo,
                base_url=base_url,
                external_ids=ids,
                max_concurrent=max_concurrent,
            )
        else:
            parser = MyHomeParser(client, repo, base_url=base_url)
            report = await parser.run()
    print(
        json.dumps(
            {"parsed": report.parsed, "new": report.new, "errors": report.errors},
            ensure_ascii=False,
        ),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Парсер myhome для n8n.")
    ap.add_argument(
        "--ingest-ids-json",
        type=Path,
        default=None,
        help="JSON-массив external_id: ингест только этих ID через GET /v1/statements/{id}.",
    )
    cli = ap.parse_args()
    try:
        asyncio.run(_async_main(ingest_ids_json=cli.ingest_ids_json))
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
