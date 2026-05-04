from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from domain.lead import Lead
from parsers.base import BaseParser
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_PUBLISHED_AT_KEYS = (
    "published_at",
    "created_at",
    "statement_date",
    "activation_date",
    "date",
)


@dataclass
class MyHomeRunReport:
    parsed: int
    new: int
    errors: list[str] = field(default_factory=list)
    leads: list[Lead] = field(default_factory=list)


def _price_slot(raw: dict[str, Any]) -> dict[str, Any]:
    block = raw.get("price")
    if not isinstance(block, dict):
        return {}
    slot = block.get("1")
    if slot is None:
        slot = block.get(1)
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


class MyHomeParser(BaseParser):
    """Парсер списка объявлений myhome.ge (HTTP API)."""

    SOURCE = "myhome"

    def __init__(
        self,
        client: httpx.AsyncClient,
        repository: LeadRepository,
        *,
        base_url: str | None = None,
    ) -> None:
        self._client = client
        self._repository = repository
        self._base_url = (base_url or "https://api-statements.tnet.ge").rstrip("/")

    def _request_headers(self) -> dict[str, str]:
        return {
            "X-Website-Key": "myhome",
            "Accept": "application/json",
            "Origin": "https://www.myhome.ge",
            "Referer": "https://www.myhome.ge/",
            "User-Agent": _DEFAULT_USER_AGENT,
        }

    def _list_params(self) -> dict[str, str | int]:
        return {
            "deal_types": 1,
            "real_estate_types": 1,
            "currency_id": 1,
            "cities": 1,
            "owner_type": "physical",
            "page": 1,
            "sort": "date_desc",
        }

    async def fetch_raw_batch(self) -> list[dict[str, Any]]:
        url = f"{self._base_url}/v1/statements/"
        response = await self._client.get(
            url,
            params=self._list_params(),
            headers=self._request_headers(),
            timeout=60.0,
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

    async def parse_lead(self, raw: dict[str, Any]) -> Lead | None:
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
        slot = _price_slot(raw)
        total = slot.get("price_total")
        per_m2 = slot.get("price_square")
        price_total = int(total) if total is not None else None
        price_m2 = int(per_m2) if per_m2 is not None else None
        published_at = _parse_published_at(raw)
        return Lead(
            source=self.SOURCE,
            external_id=external_id,
            source_listing_uuid=listing_uuid,
            price_total_usd=price_total,
            price_m2_usd=price_m2,
            published_at=published_at,
        )

    async def run(self) -> MyHomeRunReport:
        raw_list = await self.fetch_raw_batch()
        parsed = len(raw_list)
        errors: list[str] = []
        new_leads: list[Lead] = []
        for raw in raw_list:
            item_label = str(raw.get("id", "unknown"))
            try:
                lead = await self.parse_lead(raw)
                if lead is None:
                    errors.append(f"skip_invalid:{item_label}")
                    continue
                existing = await asyncio.to_thread(
                    self._repository.get_by_source_and_external_id,
                    lead.source,
                    lead.external_id,
                )
                if existing is not None:
                    continue
                saved = await asyncio.to_thread(self._repository.save, lead)
                new_leads.append(saved)
            except Exception as exc:  # noqa: BLE001 — собираем отчёт, не роняем весь пакет
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
