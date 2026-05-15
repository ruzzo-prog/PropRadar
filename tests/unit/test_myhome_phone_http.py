"""Unit-тесты HTTP phone enricher (2captcha + phone/show), без реальной сети."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest

from domain.lead import Lead, LeadStatus
from parsers.adapters.myhome.phone_http import (
    MyHomePhoneHttpEnricher,
    PhoneShowError,
    TwoCaptchaClient,
    httpx_client_kwargs_from_settings,
    load_access_token,
    post_phone_show,
)
from repositories.base import LeadRepository


class _PhoneRepo(LeadRepository):
    def __init__(self, leads: list[Lead]) -> None:
        self._leads = {lead.id: lead for lead in leads if lead.id}
        self.updates: list[Lead] = []
        self.retries: dict[UUID, int] = {}

    def get_by_id(self, entity_id: UUID) -> Lead | None:
        return self._leads.get(entity_id)

    def save(self, entity: Lead) -> Lead:
        raise NotImplementedError

    def get_by_source_and_external_id(self, source: str, external_id: str) -> Lead | None:
        return None

    def list_pending_detail_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def list_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return list(self._leads.values())

    def claim_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return list(self._leads.values())[:limit]

    def increment_phone_retry(self, lead_id: UUID) -> int:
        self.retries[lead_id] = self.retries.get(lead_id, 0) + 1
        lead = self._leads[lead_id]
        lead = lead.model_copy(update={"phone_retries": self.retries[lead_id]})
        self._leads[lead_id] = lead
        return self.retries[lead_id]

    def mark_phone_enrich_exhausted(self, lead_id: UUID) -> None:
        lead = self._leads[lead_id]
        self._leads[lead_id] = lead.model_copy(update={"status_reason": "phone_enrich_failed"})

    def list_pending_pdf_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def update_enriched_fields(self, entity: Lead) -> Lead:
        self.updates.append(entity)
        if entity.id:
            self._leads[entity.id] = entity
        return entity

    def list_external_ids_by_source_and_status(
        self,
        source: str,
        status: LeadStatus,
    ) -> list[str]:
        return []

    def mark_leads_by_external_ids(
        self,
        source: str,
        external_ids: list[str],
        *,
        status: LeadStatus,
        status_reason: str | None = None,
    ) -> int:
        return 0


def test_load_access_token_from_storage(tmp_path: Path) -> None:
    session = {
        "cookies": [
            {"name": "AccessToken", "value": "jwt-token-value", "domain": ".tnet.ge"},
        ],
    }
    path = tmp_path / "session.json"
    path.write_text(json.dumps(session), encoding="utf-8")
    assert load_access_token(path) == "jwt-token-value"


def test_post_phone_show_parses_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/statements/phone/show")
        assert "statement_uuid=" in str(request.url)
        assert request.headers.get("global-authorization") == "jwt"
        body = json.loads(request.content.decode())
        assert body["response_token"] == "captcha-token"
        return httpx.Response(
            200,
            json={"result": True, "data": {"phone_number": "+995551820088"}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    phone = post_phone_show(
        client,
        base_url="https://api-statements.tnet.ge",
        statement_uuid=uuid4(),
        captcha_token="captcha-token",
        access_token="jwt",
    )
    assert phone == "+995551820088"


def test_post_phone_show_401_raises_retryable() -> None:
    transport = httpx.MockTransport(lambda _req: httpx.Response(401))
    client = httpx.Client(transport=transport)
    with pytest.raises(PhoneShowError) as exc_info:
        post_phone_show(
            client,
            base_url="https://api-statements.tnet.ge",
            statement_uuid=uuid4(),
            captcha_token="x",
            access_token="jwt",
        )
    assert exc_info.value.retryable is True


def test_post_phone_show_400_raises_retryable() -> None:
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(400, json={"result": False}),
    )
    client = httpx.Client(transport=transport)
    with pytest.raises(PhoneShowError, match="phone_api_http_400"):
        post_phone_show(
            client,
            base_url="https://api-statements.tnet.ge",
            statement_uuid=uuid4(),
            captcha_token="x",
            access_token="jwt",
        )


def test_enrich_one_success() -> None:
    lid = uuid4()
    su = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="123",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=su,
    )
    repo = _PhoneRepo([lead])

    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
        http_client=httpx.Client(),
    )
    with (
        patch.object(enricher, "_enrich_one", return_value=None) as one,
        patch(
            "parsers.adapters.myhome.phone_http.load_access_token",
            return_value="jwt",
        ),
    ):
        report = enricher.enrich_leads([lead], source="myhome")
    assert report.enriched == 1
    assert report.failed == 0
    one.assert_called_once()


def test_two_captcha_solve_parses_ready_response() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "createTask" in str(request.url):
            return httpx.Response(200, json={"errorId": 0, "taskId": 42})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"errorId": 0, "status": "processing"})
        return httpx.Response(
            200,
            json={
                "errorId": 0,
                "status": "ready",
                "solution": {"gRecaptchaResponse": "tok"},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    captcha = TwoCaptchaClient("api-key", site_key="site-key", http_client=client)
    try:
        with patch("parsers.adapters.myhome.phone_http.time.sleep"):
            assert captcha.solve_recaptcha_v3() == "tok"
    finally:
        captcha.close()


def test_httpx_client_kwargs_includes_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLAYWRIGHT_PROXY_SERVER", "http://proxy.example:8080")
    monkeypatch.setenv("PLAYWRIGHT_PROXY_USER", "user")
    monkeypatch.setenv("PLAYWRIGHT_PROXY_PASS", "secret")
    monkeypatch.setenv("APP_ENV", "development")
    kw = httpx_client_kwargs_from_settings()
    assert kw["proxy"] == "http://user:secret@proxy.example:8080"


def test_enrich_leads_passes_same_client_kwargs_to_main_and_captcha() -> None:
    """Оба httpx.Client (myhome + 2captcha) получают одинаковые kwargs (в т.ч. proxy)."""
    client_kw = {"timeout": 60.0, "proxy": "http://proxy.example:8080"}
    lid = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="1",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=uuid4(),
    )
    repo = _PhoneRepo([lead])
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )
    with (
        patch(
            "parsers.adapters.myhome.phone_http.httpx_client_kwargs_from_settings",
            return_value=client_kw,
        ),
        patch("parsers.adapters.myhome.phone_http.httpx.Client") as client_cls,
        patch(
            "parsers.adapters.myhome.phone_http.load_access_token",
            return_value="jwt",
        ),
        patch.object(enricher, "_enrich_one", return_value=None),
    ):
        client_cls.return_value = MagicMock()
        enricher.enrich_leads([lead], source="myhome")
    assert client_cls.call_count == 2
    assert client_cls.call_args_list[0].kwargs == client_kw
    assert client_cls.call_args_list[1].kwargs == client_kw


def test_enrich_one_401_increments_phone_retries() -> None:
    lid = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="401-lead",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=uuid4(),
        phone_retries=0,
    )
    repo = _PhoneRepo([lead])
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
        http_client=httpx.Client(),
    )
    with (
        patch(
            "parsers.adapters.myhome.phone_http.resolve_statement_uuid",
            return_value=uuid4(),
        ),
        patch(
            "parsers.adapters.myhome.phone_http.TwoCaptchaClient.solve_recaptcha_v3",
            return_value="captcha-tok",
        ),
        patch(
            "parsers.adapters.myhome.phone_http.post_phone_show",
            side_effect=PhoneShowError("phone_api_unauthorized", retryable=True),
        ),
    ):
        err = enricher._enrich_one(
            httpx.Client(),
            MagicMock(),
            "jwt",
            lead,
            "myhome",
        )
    assert err == "401-lead:phone_api_unauthorized"
    assert repo.retries[lid] == 1
    assert lead.status_reason is None


def test_load_access_token_failure_does_not_create_httpx_clients() -> None:
    created: list[object] = []

    def _fake_client(**_kwargs: object) -> MagicMock:
        created.append(object())
        return MagicMock()

    lid = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="1",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=uuid4(),
    )
    repo = _PhoneRepo([lead])
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=Path("/missing/session.json"),
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )
    with (
        patch("parsers.adapters.myhome.phone_http.httpx.Client", side_effect=_fake_client),
        patch(
            "parsers.adapters.myhome.phone_http.load_access_token",
            side_effect=PhoneShowError("access_token_missing", retryable=False),
        ),
    ):
        report = enricher.enrich_leads([lead], source="myhome")
    assert report.failed == 1
    assert "access_token_missing" in report.errors[0]
    assert created == []


def test_enrich_leads_creates_two_httpx_clients_per_lead() -> None:
    client_kw = {"timeout": 60.0}
    leads = [
        Lead(
            id=uuid4(),
            source="myhome",
            external_id="a",
            status=LeadStatus.NEW,
            score=0,
            source_listing_uuid=uuid4(),
        ),
        Lead(
            id=uuid4(),
            source="myhome",
            external_id="b",
            status=LeadStatus.NEW,
            score=0,
            source_listing_uuid=uuid4(),
        ),
    ]
    repo = _PhoneRepo(leads)
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=2,
    )
    with (
        patch(
            "parsers.adapters.myhome.phone_http.httpx_client_kwargs_from_settings",
            return_value=client_kw,
        ),
        patch("parsers.adapters.myhome.phone_http.httpx.Client") as client_cls,
        patch(
            "parsers.adapters.myhome.phone_http.load_access_token",
            return_value="jwt",
        ),
        patch.object(enricher, "_enrich_one", return_value=None),
    ):
        client_cls.return_value = MagicMock()
        report = enricher.enrich_leads(leads, source="myhome")
    assert report.enriched == 2
    assert client_cls.call_count == 4


def test_two_captcha_init_failure_closes_both_httpx_clients() -> None:
    closed = 0

    class _TrackingClient:
        def close(self) -> None:
            nonlocal closed
            closed += 1

    lead = Lead(
        id=uuid4(),
        source="myhome",
        external_id="x",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=uuid4(),
    )
    enricher = MyHomePhoneHttpEnricher(
        _PhoneRepo([lead]),  # repository
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
    )

    def _boom(*_a, **_k):
        raise ValueError("captcha_init_failed")

    with (
        patch(
            "parsers.adapters.myhome.phone_http.httpx.Client",
            side_effect=lambda **_kw: _TrackingClient(),
        ),
        patch(
            "parsers.adapters.myhome.phone_http.TwoCaptchaClient",
            side_effect=_boom,
        ),
        pytest.raises(ValueError, match="captcha_init_failed"),
    ):
        enricher._enrich_one_isolated(
            lead,
            access_token="jwt",
            source="myhome",
            client_kw={"timeout": 60.0},
        )
    assert closed == 2


def test_enrich_batch_claim_limit_one_per_slot() -> None:
    repo = MagicMock(spec=LeadRepository)
    repo.claim_pending_phone_enrichment.return_value = [
        Lead(
            id=uuid4(),
            source="myhome",
            external_id="1",
            status=LeadStatus.NEW,
            score=0,
            source_listing_uuid=uuid4(),
        ),
    ]
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=5,
    )
    with (
        patch(
            "parsers.adapters.myhome.phone_http.load_access_token",
            return_value="jwt",
        ),
        patch.object(enricher, "_enrich_one_isolated", return_value=None) as enrich_mock,
    ):
        report = enricher.enrich_batch("myhome", limit=5)
    assert report.enriched == 5
    assert repo.claim_pending_phone_enrichment.call_count == 5
    for call in repo.claim_pending_phone_enrichment.call_args_list:
        assert call.kwargs.get("limit") == 1


def test_enrich_batch_runs_up_to_max_workers_concurrently() -> None:
    lock = threading.Lock()
    in_flight = 0
    peak = 0

    def _track_enrich(*_a, **_k):
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.08)
        with lock:
            in_flight -= 1
        return None

    lead = Lead(
        id=uuid4(),
        source="myhome",
        external_id="p",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=uuid4(),
    )
    repo = MagicMock(spec=LeadRepository)
    repo.claim_pending_phone_enrichment.return_value = [lead]
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=5,
    )
    with (
        patch(
            "parsers.adapters.myhome.phone_http.load_access_token",
            return_value="jwt",
        ),
        patch.object(enricher, "_enrich_one_isolated", side_effect=_track_enrich),
    ):
        report = enricher.enrich_batch("myhome", limit=5)
    assert report.enriched == 5
    assert peak >= 5


def test_increment_retry_on_phone_show_error() -> None:
    lid = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="999",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=uuid4(),
    )
    repo = _PhoneRepo([lead])
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url="https://api-statements.tnet.ge",
        session_path=None,
        twocaptcha_api_key="key",
        recaptcha_site_key="site",
        max_workers=1,
        http_client=httpx.Client(),
    )
    with patch(
        "parsers.adapters.myhome.phone_http.resolve_statement_uuid",
        side_effect=PhoneShowError("phone_api_http_400", retryable=True),
    ):
        err = enricher._enrich_one(
            httpx.Client(),
            MagicMock(),
            "jwt",
            lead,
            "myhome",
        )
    assert err is not None
    assert repo.retries[lid] == 1
