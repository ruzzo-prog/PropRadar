"""HTTP-обогащение телефона myhome.ge: 2captcha reCAPTCHA v3 + ``POST …/phone/show``.

Основной путь (~16 с/лид). Playwright fallback — ``phone.py`` (отдельная фаза воркера).
Токены и номера в логи не пишутся.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from config.settings import Settings
from domain.lead import Lead
from parsers.adapters.myhome.constants import (
    DEFAULT_ORIGIN,
    PHONE_SHOW_PATH,
    REQUEST_TIMEOUT_S,
    api_headers,
)
from parsers.adapters.myhome.enricher import fetch_statement_detail
from parsers.adapters.myhome.phone import parse_phone_response
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

TWOCAPTCHA_CREATE_URL = "https://api.2captcha.com/createTask"
TWOCAPTCHA_RESULT_URL = "https://api.2captcha.com/getTaskResult"
TWOCAPTCHA_POLL_INTERVAL_S = 3.0
TWOCAPTCHA_MAX_WAIT_S = 120.0
PHONE_ENRICH_EXHAUSTED_REASON = "phone_enrich_failed"


@dataclass
class MyHomePhoneHttpEnrichReport:
    enriched: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    retries_incremented: int = 0


class TwoCaptchaError(RuntimeError):
    """Ошибка API 2captcha (retryable)."""


class _HttpxPhoneResponseAdapter:
    """Адаптер httpx → контракт ``parse_phone_response`` (Playwright ``.status``)."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    @property
    def status(self) -> int:
        return self._response.status_code

    def json(self) -> Any:
        return self._response.json()


class PhoneShowError(RuntimeError):
    """Ошибка ``phone/show``; ``retryable`` — увеличить ``phone_retries``."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def load_access_token(session_path: Path | None) -> str:
    """Прочитать ``AccessToken`` из Playwright storage state."""
    if session_path is None or not session_path.is_file():
        msg = "myhome_session_missing"
        raise PhoneShowError(msg, retryable=False)
    storage = json.loads(session_path.read_text(encoding="utf-8"))
    token = next(
        (c["value"] for c in storage.get("cookies", []) if c.get("name") == "AccessToken"),
        None,
    )
    if not token:
        msg = "access_token_missing"
        raise PhoneShowError(msg, retryable=False)
    return str(token)


def _decode_jwt_payload_segment(segment: str) -> dict[str, Any]:
    """JWT payload segment: base64url (unpadded), not standard base64."""
    pad = "=" * (-len(segment) % 4)
    raw = base64.urlsafe_b64decode(segment + pad)
    data = json.loads(raw)
    if not isinstance(data, dict):
        msg = "jwt_payload_not_object"
        raise TypeError(msg)
    return data


def access_token_remaining_seconds(session_path: Path | None) -> float | None:
    """Секунды до ``expires_at`` JWT AccessToken в storage state; ``None`` если не прочитать."""
    if session_path is None or not session_path.is_file():
        return None
    try:
        storage = json.loads(session_path.read_text(encoding="utf-8"))
        token = next(
            (c["value"] for c in storage.get("cookies", []) if c.get("name") == "AccessToken"),
            None,
        )
        if not token:
            return None
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = _decode_jwt_payload_segment(parts[1])
        expires_at = payload.get("expires_at")
        if expires_at is None:
            return None
        return float(expires_at) - time.time()
    except Exception:
        return None


def session_needs_login(session_path: Path | None, *, min_remaining: float) -> bool:
    """Нужен ли ``myhome_login`` перед phone HTTP (как ``phone.py``, порог настраивается)."""
    if session_path is None or not session_path.is_file():
        return True
    remaining = access_token_remaining_seconds(session_path)
    if remaining is None:
        return True
    return remaining < min_remaining


def resolve_statement_uuid(
    client: httpx.Client,
    lead: Lead,
    *,
    base_url: str,
) -> UUID:
    if lead.source_listing_uuid is not None:
        return lead.source_listing_uuid
    stmt = fetch_statement_detail(
        client,
        base_url=base_url,
        external_id=lead.external_id,
    )
    raw = stmt.get("uuid")
    if not isinstance(raw, str) or not raw.strip():
        msg = "statement_uuid_missing"
        raise PhoneShowError(msg, retryable=True)
    return UUID(raw.strip())


class TwoCaptchaClient:
    """Клиент 2captcha (reCAPTCHA v3, JSON API).

    Если передан ``http_client``, владелец закрывает его снаружи; ``close()`` не трогает его.
    """

    def __init__(
        self,
        api_key: str,
        *,
        site_key: str,
        page_url: str = DEFAULT_ORIGIN,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._site_key = site_key
        self._page_url = page_url
        self._own_client = http_client is None
        self._client = http_client or httpx.Client(timeout=REQUEST_TIMEOUT_S)

    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def solve_recaptcha_v3(self, *, page_action: str = "phone_show") -> str:
        create_body: dict[str, Any] = {
            "clientKey": self._api_key,
            "task": {
                "type": "RecaptchaV3TaskProxyless",
                "websiteURL": self._page_url,
                "websiteKey": self._site_key,
                "minScore": 0.3,
                "pageAction": page_action,
            },
        }
        created = self._client.post(TWOCAPTCHA_CREATE_URL, json=create_body)
        created.raise_for_status()
        create_payload = created.json()
        if create_payload.get("errorId"):
            raise TwoCaptchaError(str(create_payload.get("errorDescription", "createTask_failed")))
        task_id = create_payload.get("taskId")
        if not task_id:
            raise TwoCaptchaError("createTask_no_task_id")

        deadline = time.monotonic() + TWOCAPTCHA_MAX_WAIT_S
        while time.monotonic() < deadline:
            time.sleep(TWOCAPTCHA_POLL_INTERVAL_S)
            result = self._client.post(
                TWOCAPTCHA_RESULT_URL,
                json={"clientKey": self._api_key, "taskId": task_id},
            )
            result.raise_for_status()
            payload = result.json()
            if payload.get("errorId"):
                raise TwoCaptchaError(str(payload.get("errorDescription", "getTaskResult_failed")))
            if payload.get("status") != "ready":
                continue
            solution = payload.get("solution")
            if not isinstance(solution, dict):
                raise TwoCaptchaError("getTaskResult_bad_solution")
            token = solution.get("gRecaptchaResponse") or solution.get("token")
            if not isinstance(token, str) or not token.strip():
                raise TwoCaptchaError("getTaskResult_empty_token")
            return token.strip()
        raise TwoCaptchaError("getTaskResult_timeout")


def post_phone_show(
    client: httpx.Client,
    *,
    base_url: str,
    statement_uuid: UUID,
    captcha_token: str,
    access_token: str,
) -> str:
    """``POST /v1/statements/phone/show`` → нормализованный номер."""
    url = f"{base_url.rstrip('/')}{PHONE_SHOW_PATH}"
    headers = {
        **api_headers(),
        "Content-Type": "application/json",
        "global-authorization": access_token,
    }
    params = {"statement_uuid": str(statement_uuid)}
    body = {"response_token": captcha_token}
    response = client.post(
        url,
        headers=headers,
        params=params,
        json=body,
        timeout=REQUEST_TIMEOUT_S,
    )
    if response.status_code == 401:
        raise PhoneShowError("phone_api_unauthorized", retryable=True)
    if response.status_code == 204:
        raise PhoneShowError("phone_api_204_no_json", retryable=True)
    if response.status_code >= 400:
        raise PhoneShowError(f"phone_api_http_{response.status_code}", retryable=True)
    return parse_phone_response(_HttpxPhoneResponseAdapter(response))


def httpx_proxy_from_settings(settings: Settings) -> str | None:
    server = settings.playwright_proxy_server
    if not server:
        return None
    user = settings.playwright_proxy_user
    password = settings.playwright_proxy_pass
    if user and password:
        if "://" in server:
            scheme, rest = server.split("://", 1)
            return f"{scheme}://{user}:{password}@{rest}"
        return f"http://{user}:{password}@{server}"
    return server


def httpx_client_kwargs_from_settings(settings: Settings | None = None) -> dict[str, Any]:
    """Общие kwargs для httpx.Client (myhome API и 2captcha)."""
    resolved = settings or Settings()
    client_kw: dict[str, Any] = {"timeout": REQUEST_TIMEOUT_S}
    proxy = httpx_proxy_from_settings(resolved)
    if proxy:
        client_kw["proxy"] = proxy
    return client_kw


class MyHomePhoneHttpEnricher:
    """Параллельное HTTP-обогащение телефона (2captcha + phone/show)."""

    def __init__(
        self,
        repository: LeadRepository,
        *,
        base_url: str,
        session_path: Path | None,
        twocaptcha_api_key: str,
        recaptcha_site_key: str,
        max_workers: int = 5,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._repository = repository
        self._base_url = base_url
        self._session_path = session_path
        self._twocaptcha_key = twocaptcha_api_key
        self._site_key = recaptcha_site_key
        self._max_workers = max(1, min(max_workers, 10))
        self._http_client = http_client

    def enrich_leads(self, leads: list[Lead], *, source: str) -> MyHomePhoneHttpEnrichReport:
        report = MyHomePhoneHttpEnrichReport()
        if not leads:
            return report

        try:
            access_token = load_access_token(self._session_path)
        except PhoneShowError as exc:
            report.failed = len(leads)
            report.errors.append(str(exc))
            return report

        client_kw = httpx_client_kwargs_from_settings()

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(
                    self._enrich_one_isolated,
                    lead,
                    access_token=access_token,
                    source=source,
                    client_kw=client_kw,
                ): lead
                for lead in leads
            }
            for fut in as_completed(futures):
                lead = futures[fut]
                try:
                    err = fut.result()
                except Exception as exc:  # noqa: BLE001
                    err = f"{lead.external_id}:{type(exc).__name__}"
                if err is None:
                    report.enriched += 1
                else:
                    report.failed += 1
                    report.errors.append(err)
        return report

    def _enrich_one_isolated(
        self,
        lead: Lead,
        *,
        access_token: str,
        source: str,
        client_kw: dict[str, Any],
    ) -> str | None:
        """Один лид в потоке: отдельные httpx.Client для myhome и 2captcha."""
        myhome_client: httpx.Client | None = None
        captcha_http: httpx.Client | None = None
        captcha: TwoCaptchaClient | None = None
        try:
            myhome_client = httpx.Client(**client_kw)
            captcha_http = httpx.Client(**client_kw)
            captcha = TwoCaptchaClient(
                self._twocaptcha_key,
                site_key=self._site_key,
                http_client=captcha_http,
            )
            return self._enrich_one(
                myhome_client,
                captcha,
                access_token,
                lead,
                source,
            )
        finally:
            if captcha is not None:
                captcha.close()
            if captcha_http is not None:
                captcha_http.close()
            if myhome_client is not None:
                myhome_client.close()

    def enrich_batch(self, source: str, *, limit: int) -> MyHomePhoneHttpEnrichReport:
        """Параллельный батч: до ``limit`` задач, каждая делает ``claim(limit=1)`` и enrich."""
        report = MyHomePhoneHttpEnrichReport()
        slots = max(1, min(limit, 500))
        if slots <= 0:
            return report

        try:
            access_token = load_access_token(self._session_path)
        except PhoneShowError as exc:
            report.failed = slots
            report.errors.append(str(exc))
            return report

        client_kw = httpx_client_kwargs_from_settings()

        def _claim_and_enrich_one() -> tuple[bool, str | None]:
            leads = self._repository.claim_pending_phone_enrichment(source, limit=1)
            if not leads:
                return False, None
            err = self._enrich_one_isolated(
                leads[0],
                access_token=access_token,
                source=source,
                client_kw=client_kw,
            )
            return True, err

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = [pool.submit(_claim_and_enrich_one) for _ in range(slots)]
            for fut in as_completed(futures):
                try:
                    claimed, err = fut.result()
                except Exception as exc:  # noqa: BLE001
                    report.failed += 1
                    report.errors.append(f"worker:{type(exc).__name__}")
                    continue
                if not claimed:
                    continue
                if err is None:
                    report.enriched += 1
                else:
                    report.failed += 1
                    report.errors.append(err)
        return report

    def _record_retry(self, lead: Lead, source: str, err: str) -> str:
        if lead.id is None:
            return err
        try:
            retries = self._repository.increment_phone_retry(lead.id)
        except ValueError:
            return err
        if retries >= 3:
            self._repository.mark_phone_enrich_exhausted(lead.id)
            logger.info(
                "phone_enrich_exhausted ext=%s retries=%s",
                lead.external_id,
                retries,
            )
        return err

    def _enrich_one(
        self,
        client: httpx.Client,
        captcha: TwoCaptchaClient,
        access_token: str,
        lead: Lead,
        source: str,
    ) -> str | None:
        if lead.id is None:
            return f"no_lead_id:{lead.external_id}"
        started = time.monotonic()
        label = f"source={source} id={lead.id} ext={lead.external_id}"
        try:
            statement_uuid = resolve_statement_uuid(
                client,
                lead,
                base_url=self._base_url,
            )
            token = captcha.solve_recaptcha_v3()
            phone = post_phone_show(
                client,
                base_url=self._base_url,
                statement_uuid=statement_uuid,
                captcha_token=token,
                access_token=access_token,
            )
            merged = lead.model_copy(update={"phone": phone})
            self._repository.update_enriched_fields(merged)
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "phone_http_ok ext=%s thread=%s latency_ms=%s",
                lead.external_id,
                threading.get_ident(),
                latency_ms,
            )
            return None
        except PhoneShowError as exc:
            logger.warning(
                "phone_http fail %s type=PhoneShowError code=%s",
                label,
                exc,
            )
            if exc.retryable:
                return self._record_retry(lead, source, f"{lead.external_id}:{exc}")
            return f"{lead.external_id}:{exc}"
        except TwoCaptchaError as exc:
            logger.warning(
                "phone_http fail %s type=TwoCaptchaError code=%s",
                label,
                exc,
            )
            return self._record_retry(lead, source, f"{lead.external_id}:{exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "phone_http fail %s type=%s",
                label,
                type(exc).__name__,
            )
            return self._record_retry(lead, source, f"{lead.external_id}:{type(exc).__name__}")
