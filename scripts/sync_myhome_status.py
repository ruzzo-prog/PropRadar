"""Сверка лидов myhome (status=new) с актуальным списком API: исчезнувшие → JSON / mark-rejected."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

from config.settings import Settings
from domain.lead import LeadStatus
from parsers.adapters.myhome.list_ids import fetch_all_external_ids_sync, list_httpx_client_kwargs
from repositories.postgres_lead_repository import PostgresLeadRepository, PostgresSessionFactory

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sync_myhome_status")

SOURCE = "myhome"
DEFAULT_REASON = "disappeared_from_api"


def _owner_name(lead: Any) -> str | None:
    j = lead.myhome_statement_json
    if not isinstance(j, dict):
        return None
    v = j.get("owner_name")
    if isinstance(v, str):
        t = v.strip()
        return t or None
    return None


def _load_id_set_from_json_path(path: Path) -> set[str]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        msg = "Ожидается JSON-массив ID"
        raise ValueError(msg)
    out: set[str] = set()
    for x in data:
        if x is None:
            continue
        out.add(str(x).strip())
    out.discard("")
    return out


def cmd_discover(
    *,
    api_ids_path: Path | None,
    fetch_api: bool,
    max_pages: int,
) -> dict[str, Any]:
    settings = Settings()
    base_url = str(settings.myhome_api_base_url).rstrip("/")
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    repo = PostgresLeadRepository(sessions)

    if fetch_api:
        with httpx.Client(**list_httpx_client_kwargs(settings)) as client:
            api_ids_list = fetch_all_external_ids_sync(
                client,
                base_url=base_url,
                since_days=None,
                max_pages=max(1, min(max_pages, 10_000)),
            )
        api_ids = set(api_ids_list)
    elif api_ids_path is not None:
        api_ids = _load_id_set_from_json_path(api_ids_path)
    else:
        msg = "Укажите --api-ids-json или --fetch-api"
        raise ValueError(msg)

    db_ids = set(repo.list_external_ids_by_source_and_status(SOURCE, LeadStatus.NEW))
    disappeared_ext = sorted(db_ids - api_ids)

    disappeared_rows: list[dict[str, Any]] = []
    for ext in disappeared_ext:
        lead = repo.get_by_source_and_external_id(SOURCE, ext)
        if lead is None:
            continue
        disappeared_rows.append(
            {
                "external_id": ext,
                "phone": lead.phone,
                "address": lead.address,
                "owner_name": _owner_name(lead),
                "lead_id": str(lead.id) if lead.id else None,
            },
        )

    return {
        "disappeared": disappeared_rows,
        "counts": {
            "api_ids": len(api_ids),
            "db_new_external_ids": len(db_ids),
            "disappeared": len(disappeared_rows),
        },
    }


def cmd_mark(
    *,
    ids_path: Path,
    reason: str,
) -> dict[str, Any]:
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    repo = PostgresLeadRepository(sessions)
    ids = sorted(_load_id_set_from_json_path(ids_path))
    updated = repo.mark_leads_by_external_ids(
        SOURCE,
        ids,
        status=LeadStatus.REJECTED,
        status_reason=reason,
    )
    return {"updated": updated, "reason": reason}


def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизация статусов myhome с API.")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="Сравнить БД и API, вывести исчезнувшие (без UPDATE).")
    d.add_argument(
        "--api-ids-json",
        type=Path,
        default=None,
        help="Файл: JSON-массив строк external_id (вывод fetch_myhome_ids).",
    )
    d.add_argument(
        "--fetch-api",
        action="store_true",
        help="Загрузить полный список ID с API (эквивалент fetch_myhome_ids.py --full).",
    )
    d.add_argument("--max-pages", type=int, default=500, help="Лимит страниц при --fetch-api.")

    m = sub.add_parser(
        "mark-rejected",
        help="После уведомления в WhatsApp: rejected + status_reason для списка external_id.",
    )
    m.add_argument(
        "--ids-json",
        type=Path,
        required=True,
        help="JSON-массив external_id для обновления.",
    )
    m.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help=f"Код причины (по умолчанию {DEFAULT_REASON}).",
    )

    args = parser.parse_args()

    if args.command == "discover" and not args.fetch_api and args.api_ids_json is None:
        print(
            json.dumps(
                {
                    "error": "missing_api_ids_source",
                    "message": "discover: укажите --api-ids-json или --fetch-api",
                },
                ensure_ascii=False,
            ),
        )
        sys.exit(2)

    try:
        if args.command == "discover":
            out = cmd_discover(
                api_ids_path=args.api_ids_json,
                fetch_api=args.fetch_api,
                max_pages=args.max_pages,
            )
        else:
            out = cmd_mark(ids_path=args.ids_json, reason=args.reason)
        print(json.dumps(out, ensure_ascii=False))
    except httpx.HTTPError:
        logger.exception("HTTP error")
        print(json.dumps({"error": "http"}, ensure_ascii=False))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fatal: %s", exc)
        err_payload: dict[str, Any] = {"error": type(exc).__name__}
        if str(exc):
            err_payload["message"] = str(exc)
        print(json.dumps(err_payload, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
