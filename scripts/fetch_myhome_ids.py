"""CLI для n8n: выгрузка external_id с myhome API (постранично)."""

from __future__ import annotations

import argparse
import json
import logging
import sys

import httpx

from config.settings import Settings
from parsers.adapters.myhome.list_ids import fetch_all_external_ids_sync

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fetch_myhome_ids")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Список ID объявлений myhome (GET /v1/statements/).",
    )
    parser.add_argument(
        "--output",
        choices=("json",),
        default="json",
        help="Формат вывода (только json-массив ID).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full",
        action="store_true",
        help="Все страницы списка без фильтра по дате (обязательно для sync исчезнувших с API).",
    )
    mode.add_argument(
        "--since-days",
        type=int,
        metavar="N",
        help=(
            "Только объявления с published_at >= сейчас − N суток "
            "(полная выгрузка страниц, фильтр на клиенте)."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Предохранитель по числу страниц API (по умолчанию 500).",
    )
    args = parser.parse_args()

    settings = Settings()
    base_url = str(settings.myhome_api_base_url).rstrip("/")

    if args.full:
        since_days: int | None = None
    elif args.since_days is not None:
        since_days = max(1, args.since_days)
    else:
        since_days = 7

    try:
        with httpx.Client() as client:
            ids = fetch_all_external_ids_sync(
                client,
                base_url=base_url,
                since_days=since_days,
                max_pages=max(1, min(args.max_pages, 10_000)),
            )
    except httpx.HTTPError:
        logger.exception("HTTP error")
        print(json.dumps([], ensure_ascii=False))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fatal: %s", exc)
        print(json.dumps([], ensure_ascii=False))
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(ids, ensure_ascii=False))


if __name__ == "__main__":
    main()
