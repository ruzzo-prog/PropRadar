"""Очередь телефона: единый claim для HTTP и Playwright."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from domain.lead import Lead, LeadStatus
from parsers.myhome import MyHomeParser
from worker.main import _run_myhome_phone_playwright


def test_playwright_phone_phase_uses_claim_not_list() -> None:
    repo = MagicMock()
    repo.claim_pending_phone_enrichment.return_value = [
        Lead(
            id=uuid4(),
            source="myhome",
            external_id="1",
            status=LeadStatus.NEW,
            score=0,
        ),
    ]
    settings = MagicMock()
    settings.myhome_session_path = None

    with patch("worker.main.MyHomePhoneEnricher") as enricher_cls:
        enricher_cls.return_value.enrich_leads.return_value = MagicMock(
            enriched=1,
            failed=0,
            errors=[],
        )
        summary = _run_myhome_phone_playwright(repo, settings, limit=10)

    repo.claim_pending_phone_enrichment.assert_called_once_with(MyHomeParser.SOURCE, limit=10)
    repo.list_pending_phone_enrichment.assert_not_called()
    assert summary["phone_playwright_enriched"] == 1
