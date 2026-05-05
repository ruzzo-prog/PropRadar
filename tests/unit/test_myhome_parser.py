from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest

from domain.lead import Lead, LeadStatus
from parsers.myhome import MyHomeParser
from repositories.base import LeadRepository


class FakeLeadRepo(LeadRepository):
    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], Lead] = {}
        self.by_id: dict[UUID, Lead] = {}
        self.save_calls = 0
        self.enrich_updates: list[Lead] = []

    def get_by_id(self, entity_id: UUID) -> Lead | None:
        return self.by_id.get(entity_id)

    def get_by_source_and_external_id(self, source: str, external_id: str) -> Lead | None:
        return self.by_key.get((source, external_id))

    def save(self, entity: Lead) -> Lead:
        self.save_calls += 1
        new_id = uuid4()
        saved = entity.model_copy(update={"id": new_id})
        self.by_key[(saved.source, saved.external_id)] = saved
        self.by_id[new_id] = saved
        return saved

    def list_pending_detail_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def list_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def list_pending_pdf_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def update_enriched_fields(self, entity: Lead) -> Lead:
        self.enrich_updates.append(entity)
        return entity

    def list_external_ids_by_source_and_status(
        self,
        source: str,
        status: LeadStatus,
    ) -> list[str]:
        return [
            ext
            for (src, ext), lead in self.by_key.items()
            if src == source and lead.status == status
        ]

    def mark_leads_by_external_ids(
        self,
        source: str,
        external_ids: list[str],
        *,
        status: LeadStatus,
        status_reason: str | None = None,
    ) -> int:
        n = 0
        for ext in external_ids:
            key = (source, ext)
            lead = self.by_key.get(key)
            if lead is None or lead.status != LeadStatus.NEW:
                continue
            upd = lead.model_copy(update={"status": status, "status_reason": status_reason})
            self.by_key[key] = upd
            if lead.id is not None:
                self.by_id[lead.id] = upd
            n += 1
        return n


@pytest.mark.asyncio
async def test_parse_lead_extracts_fields() -> None:
    parser = MyHomeParser(MagicMock(spec=httpx.AsyncClient), MagicMock(spec=LeadRepository))
    raw = {
        "id": 24552178,
        "uuid": "81046b0a-d3bb-47b6-b885-ceab47c69446",
        "price": {
            "1": {"price_total": 689000, "price_square": 9850},
            "2": {"price_total": 255626, "price_square": 3652},
        },
        "created_at": "2025-01-15T10:00:00+00:00",
    }
    lead = await parser.parse_lead(raw)
    assert lead is not None
    assert lead.external_id == "24552178"
    assert lead.source == "myhome"
    assert lead.source_listing_uuid == UUID("81046b0a-d3bb-47b6-b885-ceab47c69446")
    assert lead.price_gel == 689000
    assert lead.price_usd == 255626
    assert lead.price_m2_usd == 3652
    assert lead.published_at is not None
    assert lead.status == LeadStatus.NEW


@pytest.mark.asyncio
async def test_fetch_raw_batch_parses_response() -> None:
    payload: dict[str, Any] = {
        "result": True,
        "data": {
            "data": [
                {"id": 1, "uuid": "00000000-0000-4000-8000-000000000001", "price": {"1": {}}},
            ],
        },
    }
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    parser = MyHomeParser(client, MagicMock(spec=LeadRepository))
    items = await parser.fetch_raw_batch()
    assert len(items) == 1
    assert items[0]["id"] == 1
    client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_dedup_single_save() -> None:
    repo = FakeLeadRepo()
    item = {
        "id": 42,
        "uuid": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
        "price": {
            "1": {"price_total": 280, "price_square": 28},
            "2": {"price_total": 100, "price_square": 10},
        },
    }
    payload = {"result": True, "data": {"data": [item, item]}}
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    client = MagicMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=response)
    parser = MyHomeParser(client, repo)
    report = await parser.run()
    assert report.parsed == 2
    assert report.new == 1
    assert repo.save_calls == 1
