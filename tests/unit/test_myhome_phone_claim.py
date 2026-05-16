"""Резерв очереди телефона: claim + sweep + release после ошибки."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from domain.lead import Lead, LeadStatus
from parsers.adapters.myhome.phone_http import MyHomePhoneHttpEnricher, PhoneShowError


def test_enrich_batch_sweeps_stale_before_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = MagicMock()
    repo.sweep_stale_phone_enriching.return_value = 2
    repo.claim_pending_phone_enrichment.return_value = []

    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )
    monkeypatch.setattr(
        "parsers.adapters.myhome.phone_http.load_access_token",
        lambda _p: "jwt",
    )
    report = enricher.enrich_batch("myhome", limit=3)

    repo.sweep_stale_phone_enriching.assert_called_once_with("myhome")
    assert report.enriched == 0


def test_record_retry_uses_release_not_increment() -> None:
    repo = MagicMock()
    repo.release_phone_enrich_after_failure.return_value = 2
    lid = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="9",
        status=LeadStatus.NEW,
        score=0,
    )
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )
    err = enricher._record_retry(lead, "myhome", "x:fail")
    assert err == "x:fail"
    repo.release_phone_enrich_after_failure.assert_called_once_with(lid)
    repo.increment_phone_retry.assert_not_called()


def test_enrich_batch_claims_once_per_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Два слота — два claim; без повторного claim одного id в одном батче (mock)."""
    repo = MagicMock()
    repo.sweep_stale_phone_enriching.return_value = 0
    ids = [uuid4(), uuid4()]
    leads = [
        Lead(id=ids[0], source="myhome", external_id="a", status=LeadStatus.NEW, score=0),
        Lead(id=ids[1], source="myhome", external_id="b", status=LeadStatus.NEW, score=0),
    ]
    repo.claim_pending_phone_enrichment.side_effect = [[leads[0]], [leads[1]], []]

    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )
    monkeypatch.setattr(
        "parsers.adapters.myhome.phone_http.load_access_token",
        lambda _p: "jwt",
    )
    monkeypatch.setattr(enricher, "_enrich_one_isolated", lambda *a, **k: None)
    report = enricher.enrich_batch("myhome", limit=2)

    assert report.enriched == 2
    assert repo.claim_pending_phone_enrichment.call_count == 2


def test_load_access_token_failure_does_not_sweep_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )
    def _raise_missing(_path: object) -> str:
        raise PhoneShowError("missing", retryable=False)

    monkeypatch.setattr(
        "parsers.adapters.myhome.phone_http.load_access_token",
        _raise_missing,
    )
    report = enricher.enrich_batch("myhome", limit=2)

    repo.sweep_stale_phone_enriching.assert_called_once()
    repo.claim_pending_phone_enrichment.assert_not_called()
    assert report.failed == 2
