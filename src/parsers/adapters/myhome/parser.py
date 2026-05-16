"""Парсинг списка объявлений myhome.ge через GET /v1/statements/ (без браузера)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from domain.lead import Lead
from parsers.adapters.myhome.constants import LIST_PATH, REQUEST_TIMEOUT_S, api_headers
from parsers.adapters.myhome.statement_snapshot import resolve_rooms
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

_PUBLISHED_AT_KEYS = (
    "published_at",
    "created_at",
    "statement_date",
    "activation_date",
    "date",
    "last_updated",
)


@dataclass
class MyHomeRunReport:
    parsed: int
    new: int
    errors: list[str] = field(default_factory=list)
    leads: list[Lead] = field(default_factory=list)


def _price_slot(raw: dict[str, Any], currency_key: str = "1") -> dict[str, Any]:
    block = raw.get("price")
    if not isinstance(block, dict):
        return {}
    slot = block.get(currency_key)
    if slot is None and currency_key.isdigit():
        slot = block.get(int(currency_key))
    return slot if isinstance(slot, dict) else {}


def _parse_published_at(raw: dict[str, Any]) -> datetime | None:
    for key in _PUBLISHED_AT_KEYS:
        val = raw.get(key)
        if val is None:
            continue
        if isinstance(val, (int, float)):
            ts = float(val)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=UTC)
        if isinstance(val, str):
            text = val.strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
    return None


def parse_list_item(raw: dict[str, Any], *, source: str = "myhome") -> Lead | None:
    """Преобразовать элемент списка API в черновой Lead (GEL слот ``1``, USD слот ``2``)."""
    raw_id = raw.get("id")
    if raw_id is None:
        return None
    external_id = str(raw_id)
    listing_uuid: UUID | None = None
    uuid_val = raw.get("uuid")
    if isinstance(uuid_val, str) and uuid_val:
        try:
            listing_uuid = UUID(uuid_val)
        except ValueError:
            listing_uuid = None
    slot_gel = _price_slot(raw, "1")
    slot_usd = _price_slot(raw, "2")
    gel_total = slot_gel.get("price_total")
    usd_total = slot_usd.get("price_total")
    per_m2_usd = slot_usd.get("price_square")
    price_gel = int(gel_total) if gel_total is not None else None
    price_usd_val = int(usd_total) if usd_total is not None else None
    price_m2 = int(per_m2_usd) if per_m2_usd is not None else None
    published_at = _parse_published_at(raw)
    rooms = resolve_rooms(room=raw.get("room"), room_type_id=raw.get("room_type_id"))
    return Lead(
        source=source,
        external_id=external_id,
        source_listing_uuid=listing_uuid,
        price_gel=price_gel,
        price_usd=price_usd_val,
        price_m2_usd=price_m2,
        published_at=published_at,
        rooms=rooms,
    )


async def fetch_raw_list_batch(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    list_params: dict[str, str | int] | None = None,
) -> list[dict[str, Any]]:
    """Загрузить одну страницу списка (``data.data``)."""
    url = f"{base_url.rstrip('/')}{LIST_PATH}"
    params = list_params or {
        "deal_types": 1,
        "real_estate_types": 1,
        "currency_id": 1,
        "cities": 1,
        "owner_type": "physical",
        "page": 1,
        "sort": "date_desc",
    }
    response = await client.get(
        url,
        params=params,
        headers=api_headers(),
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") is not True:
        msg = "myhome API returned result!=true"
        raise ValueError(msg)
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    items = data.get("data")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


async def run_list_pipeline(
    client: httpx.AsyncClient,
    repository: LeadRepository,
    *,
    base_url: str,
    source: str = "myhome",
    fetch_batch: Callable[[httpx.AsyncClient, str], Awaitable[list[dict[str, Any]]]] | None = None,
) -> MyHomeRunReport:
    """Сохранить новые лиды; дубликаты ``(source, external_id)`` отбрасываются."""
    fetcher = fetch_batch or (
        lambda c, u: fetch_raw_list_batch(c, base_url=u)
    )
    raw_list = await fetcher(client, base_url)
    parsed = len(raw_list)
    errors: list[str] = []
    new_leads: list[Lead] = []
    seen_ext: set[str] = set()
    for raw in raw_list:
        item_label = str(raw.get("id", "unknown"))
        try:
            lead = parse_list_item(raw, source=source)
            if lead is None:
                errors.append(f"skip_invalid:{item_label}")
                continue
            if lead.external_id in seen_ext:
                continue
            seen_ext.add(lead.external_id)
            existing = await asyncio.to_thread(
                repository.get_by_source_and_external_id,
                lead.source,
                lead.external_id,
            )
            if existing is not None:
                continue
            saved = await asyncio.to_thread(repository.save, lead)
            new_leads.append(saved)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "myhome item error id=%s type=%s",
                item_label,
                type(exc).__name__,
            )
            errors.append(f"item:{item_label}:{type(exc).__name__}")
    logger.info(
        "myhome batch done parsed=%s new=%s err_count=%s",
        parsed,
        len(new_leads),
        len(errors),
    )
    return MyHomeRunReport(parsed=parsed, new=len(new_leads), errors=errors, leads=new_leads)
