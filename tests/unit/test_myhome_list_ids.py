from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from tests.unit.test_myhome_parser import FakeLeadRepo

from domain.lead import Lead, LeadStatus
from parsers.adapters.myhome.list_ids import (
    _fetch_page,
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


def test_fetch_page_applies_default_filters_to_query_params() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json={"result": True, "data": {"data": []}})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        _fetch_page(client, base_url="https://api-statements.tnet.ge", page=1)
    assert captured["cities"] == "1"
    assert captured["real_estate_types"] == "1"
    assert captured["owner_type"] == "physical"


def test_fetch_all_external_ids_rejects_unsupported_filter() -> None:
    transport = _handler_factory()
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError, match="Unsupported city"):
            fetch_all_external_ids_sync(
                client,
                base_url="https://api-statements.tnet.ge",
                city="batumi",
            )


def test_fetch_all_external_ids_rejects_unsupported_object_type() -> None:
    transport = _handler_factory()
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError, match="Unsupported object_type"):
            fetch_all_external_ids_sync(
                client,
                base_url="https://api-statements.tnet.ge",
                object_type="house",
            )


def test_fetch_all_external_ids_applies_limit() -> None:
    transport = _handler_factory()
    with httpx.Client(transport=transport) as client:
        ids = fetch_all_external_ids_sync(
            client,
            base_url="https://api-statements.tnet.ge",
            limit=1,
            max_pages=5,
        )
    assert ids == ["24552178"]


def test_fetch_all_external_ids_forwards_filters_for_limit_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_fetch_all_list_items_sync(client, **kwargs):
        captured.update(kwargs)
        return [
            {"id": 111, "price": {"1": {}}, "created_at": "2025-01-15T10:00:00+00:00"},
        ]

    monkeypatch.setattr(
        "parsers.adapters.myhome.list_ids.fetch_all_list_items_sync",
        _fake_fetch_all_list_items_sync,
    )
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
        ids = fetch_all_external_ids_sync(
            client,
            base_url="https://api-statements.tnet.ge",
            city="tbilisi",
            category="apartment",
            object_type="apartment",
            seller_type="private",
            limit=None,
        )
    assert ids == ["111"]
    assert captured["city"] == "tbilisi"
    assert captured["category"] == "apartment"
    assert captured["object_type"] == "apartment"
    assert captured["seller_type"] == "private"


def test_raw_items_to_external_ids_since_days_filters_inside_window(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen_now = datetime(2025, 1, 20, 15, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "parsers.adapters.myhome.list_ids._utc_now",
        lambda: frozen_now,
    )
    rows = [
        {"id": 1, "price": {"1": {}}, "created_at": "2025-01-19T00:00:00+00:00"},
        {"id": 2, "price": {"1": {}}, "created_at": "2025-01-05T00:00:00+00:00"},
        {"id": 3, "price": {"1": {}}},
    ]
    ids = raw_items_to_external_ids(rows, since_days=7)
    assert ids == ["1"]


def test_raw_items_to_external_ids_since_days_boundary_includes_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen_now = datetime(2025, 1, 20, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "parsers.adapters.myhome.list_ids._utc_now",
        lambda: frozen_now,
    )
    rows = [{"id": 9, "price": {"1": {}}, "created_at": "2025-01-13T12:00:00+00:00"}]
    ids = raw_items_to_external_ids(rows, since_days=7)
    assert ids == ["9"]


def test_fetch_all_external_ids_respects_since_days(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen_now = datetime(2025, 1, 20, tzinfo=UTC)
    monkeypatch.setattr(
        "parsers.adapters.myhome.list_ids._utc_now",
        lambda: frozen_now,
    )

    def _fake_fetch_all_list_items_sync(_client: httpx.Client, **kwargs: object) -> list:
        assert kwargs.get("seller_type") == "private"
        return [
            {"id": 100, "price": {"1": {}}, "created_at": "2025-01-18T00:00:00+00:00"},
            {"id": 101, "price": {"1": {}}, "created_at": "2025-01-01T00:00:00+00:00"},
        ]

    monkeypatch.setattr(
        "parsers.adapters.myhome.list_ids.fetch_all_list_items_sync",
        _fake_fetch_all_list_items_sync,
    )
    transport = httpx.MockTransport(lambda _req: httpx.Response(200))
    with httpx.Client(transport=transport) as client:
        ids = fetch_all_external_ids_sync(
            client,
            base_url="https://api-statements.tnet.ge",
            since_days=10,
            max_pages=5,
        )
    assert ids == ["100"]
