from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from tests.unit.test_myhome_parser import FakeLeadRepo

from domain.lead import LeadStatus
from parsers.adapters.myhome import ingest_detail


def test_statement_id_matches_request_numeric_equivalence() -> None:
    assert ingest_detail._statement_id_matches_request("24552178", 24552178) is True
    assert ingest_detail._statement_id_matches_request(" 24552178 ", "24552178") is True
    assert ingest_detail._statement_id_matches_request("1", "999") is False


@pytest.mark.asyncio
async def test_ingest_persists_requested_external_id_not_response_variant() -> None:
    """В БД пишется тот же external_id, что в запросе (ключ дедупликации)."""
    repo = FakeLeadRepo()
    stmt = {
        "id": 24552178,
        "uuid": "81046b0a-d3bb-47b6-b885-ceab47c69446",
        "price": {"1": {"price_total": 100}},
        "address": "Тестовая 1",
        "comment": "x",
        "area": 50,
    }

    async def fake_fetch(
        _client: httpx.AsyncClient,
        *,
        base_url: str,
        external_id: str,
    ) -> dict:
        assert external_id == "24552178"
        return dict(stmt)

    client = MagicMock(spec=httpx.AsyncClient)
    with patch.object(ingest_detail, "fetch_statement_detail_async", side_effect=fake_fetch):
        report = await ingest_detail.ingest_new_leads_by_detail_ids(
            client,
            repo,
            base_url="https://api-statements.tnet.ge",
            external_ids=["24552178"],
        )

    assert report.new == 1
    saved = repo.by_key[("myhome", "24552178")]
    assert saved.external_id == "24552178"
    assert saved.status == LeadStatus.NEW
