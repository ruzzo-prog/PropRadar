from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from tests.unit.test_myhome_parser import FakeLeadRepo

from domain.lead import Lead, LeadStatus
from parsers.adapters.myhome.list_ids import (
    fetch_all_external_ids_sync,
    raw_items_to_external_ids,
)


def _handler_factory() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(
                200,
                json={
                    "result": True,
                    "data": {
                        "data": [
                            {
                                "id": 24552178,
                                "uuid": "81046b0a-d3bb-47b6-b885-ceab47c69446",
                                "price": {"1": {"price_total": 100, "price_square": 1}},
                                "created_at": "2025-01-15T10:00:00+00:00",
                            },
                        ],
                    },
                },
            )
        return httpx.Response(200, json={"result": True, "data": {"data": []}})

    return httpx.MockTransport(handler)


def test_fetch_all_external_ids_paginates_until_empty() -> None:
    transport = _handler_factory()
    with httpx.Client(transport=transport) as client:
        ids = fetch_all_external_ids_sync(
            client,
            base_url="https://api-statements.tnet.ge",
            since_days=None,
            max_pages=5,
        )
    assert ids == ["24552178"]


def test_raw_items_since_days_excludes_old() -> None:
    now = datetime.now(UTC)
    new_item = {
        "id": 100,
        "price": {"1": {}},
        "created_at": (now - timedelta(days=1)).isoformat(),
    }
    old_item = {
        "id": 200,
        "price": {"1": {}},
        "created_at": (now - timedelta(days=30)).isoformat(),
    }
    ids = raw_items_to_external_ids([new_item, old_item], since_days=7)
    assert ids == ["100"]


def test_fake_repo_mark_only_new() -> None:
    repo = FakeLeadRepo()
    old_id = uuid4()
    keep = Lead(
        id=old_id,
        source="myhome",
        external_id="1",
        status=LeadStatus.NEW,
    )
    repo.by_key[("myhome", "1")] = keep
    repo.by_id[old_id] = keep
    n = repo.mark_leads_by_external_ids(
        "myhome",
        ["1"],
        status=LeadStatus.REJECTED,
        status_reason="disappeared_from_api",
    )
    assert n == 1
    updated = repo.by_key[("myhome", "1")]
    assert updated.status == LeadStatus.REJECTED
    assert updated.status_reason == "disappeared_from_api"
