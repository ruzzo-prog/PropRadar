"""Ингест новых лидов myhome по ``GET /v1/statements/{id}`` (без списка страницы 1)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from domain.lead import Lead, LeadStatus
from parsers.adapters.myhome.constants import DETAIL_PATH_TMPL, REQUEST_TIMEOUT_S, api_headers
from parsers.adapters.myhome.enricher import statement_to_lead_updates
from parsers.adapters.myhome.parser import MyHomeRunReport
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)


def _statement_id_matches_request(requested_external_id: str, statement_id: Any) -> bool:
    """Сопоставить ID из запроса с полем ``statement.id`` (строка / int, без ведущих нулей)."""
    req = requested_external_id.strip()
    if req == str(statement_id).strip():
        return True
    try:
        return int(req) == int(statement_id)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return False


async def fetch_statement_detail_async(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    external_id: str,
) -> dict[str, Any]:
    path = DETAIL_PATH_TMPL.format(statement_id=external_id)
    url = f"{base_url.rstrip('/')}{path}"
    response = await client.get(url, headers=api_headers(), timeout=REQUEST_TIMEOUT_S)
    response.raise_for_status()
    body = response.json()
    if body.get("result") is not True:
        raise ValueError("myhome_detail_result_not_true")
    data = body.get("data")
    if not isinstance(data, dict):
        raise ValueError("myhome_detail_data_shape")
    stmt = data.get("statement")
    if not isinstance(stmt, dict):
        raise ValueError("myhome_detail_statement_shape")
    return stmt


async def ingest_new_leads_by_detail_ids(
    client: httpx.AsyncClient,
    repository: LeadRepository,
    *,
    base_url: str,
    external_ids: list[str],
    source: str = "myhome",
) -> MyHomeRunReport:
    """Для каждого ID: если лида ещё нет — загрузить карточку и ``save``."""
    errors: list[str] = []
    new_leads: list[Lead] = []
    seen: set[str] = set()

    for eid in external_ids:
        ext = str(eid).strip()
        if not ext or ext in seen:
            continue
        seen.add(ext)
        try:
            existing = await asyncio.to_thread(
                repository.get_by_source_and_external_id,
                source,
                ext,
            )
            if existing is not None:
                continue
            stmt = await fetch_statement_detail_async(
                client,
                base_url=base_url,
                external_id=ext,
            )
            raw_id = stmt.get("id")
            if raw_id is None:
                errors.append(f"detail_no_id:{ext}")
                continue
            if not _statement_id_matches_request(ext, raw_id):
                errors.append(f"detail_id_mismatch:{ext}:{raw_id}")
                continue
            updates = statement_to_lead_updates(stmt)
            base_lead = Lead(
                source=source,
                external_id=ext,
                status=LeadStatus.NEW,
            )
            merged = base_lead.model_copy(update=updates)
            saved = await asyncio.to_thread(repository.save, merged)
            new_leads.append(saved)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest detail fail ext=%s type=%s", ext, type(exc).__name__)
            errors.append(f"{ext}:{type(exc).__name__}")

    parsed = len(seen)
    return MyHomeRunReport(parsed=parsed, new=len(new_leads), errors=errors, leads=new_leads)
