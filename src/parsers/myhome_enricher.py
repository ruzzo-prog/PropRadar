"""Обогащение лидов myhome.ge: страница объявления + телефон через Playwright."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import Page, Response, sync_playwright

from domain.lead import Lead
from parsers.exceptions import SessionExpiredError
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

_LISTING_PATH = "/nedvizhimost/prodazha/kvartira/{external_id}"
_PHONE_URL_PART = "statements/phone/show"
_OWNER_MARKERS = ("я собственник", "ვარ მესაკუთრე")


def listing_url(external_id: str, *, locale: str = "ru") -> str:
    base = "https://www.myhome.ge"
    loc = locale.strip("/") or "ru"
    return f"{base}/{loc}{_LISTING_PATH.format(external_id=external_id)}"


def extract_details_from_page_text(text: str) -> dict[str, object]:
    """Извлечь поля из видимого текста страницы (юнит-тестируемая чистая функция)."""
    normalized = re.sub(r"\s+", " ", text).strip()
    lower = normalized.lower()

    area_m2: float | None = None
    m_area = re.search(r"(\d+[.,]?\d*)\s*(?:м²|м2|m²|kvm|кв\.?\s*м)", lower, re.I)
    if m_area:
        try:
            area_m2 = float(m_area.group(1).replace(",", "."))
        except ValueError:
            area_m2 = None

    rooms: int | None = None
    m_rooms = re.search(r"(\d+)\s*[-–]?\s*(?:комн|ოთახი)", lower, re.I)
    if m_rooms:
        rooms = int(m_rooms.group(1))

    floor: str | None = None
    m_floor = re.search(
        r"(?:этаж|სართული)[:\s]+(\d+\s*/\s*\d+|\d+)",
        text,
        re.I,
    )
    if m_floor:
        floor = m_floor.group(1).replace(" ", "")

    address: str | None = None
    m_addr = re.search(
        r"(?:адрес|მისამართი)\s*[:\s]+(.{3,120}?)(?=(?:район|რაიონი|площадь|фото|$))",
        text,
        re.I | re.DOTALL,
    )
    if m_addr:
        address = re.sub(r"\s+", " ", m_addr.group(1)).strip()

    district: str | None = None
    m_dist = re.search(
        r"(?:район|რაიონი)\s*[:\s]+(.{2,80}?)(?=(?:адрес|площадь|этаж|$))",
        text,
        re.I | re.DOTALL,
    )
    if m_dist:
        district = re.sub(r"\s+", " ", m_dist.group(1)).strip()

    is_owner = any(m in lower for m in _OWNER_MARKERS)

    description: str | None = None
    if len(normalized) > 80:
        description = normalized[:8000]

    return {
        "address": address,
        "district": district,
        "area_m2": area_m2,
        "rooms": rooms,
        "floor": floor,
        "description": description,
        "is_owner": is_owner,
    }


def _visible_text(page: Page) -> str:
    try:
        return page.locator("main").first.inner_text(timeout=25_000)
    except Exception:
        return page.locator("body").inner_text(timeout=25_000)


def _parse_phone_response(response: Response) -> str:
    if response.status == 401:
        raise SessionExpiredError()
    if response.status >= 400:
        msg = f"phone_api_http_{response.status}"
        raise RuntimeError(msg)
    payload = response.json()
    if payload.get("result") is not True:
        raise RuntimeError("phone_api_denied")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("phone_api_shape")
    raw = data.get("phone_number")
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("phone_api_empty")
    return raw.strip()


def _click_show_phone(page: Page) -> str:
    btn = page.get_by_role("button", name=re.compile(r"номер|телефон|ნომერი", re.I))
    with page.expect_response(
        lambda r: _PHONE_URL_PART in r.url and r.request.method == "POST",
        timeout=45_000,
    ) as resp_wrap:
        btn.first.click(timeout=20_000)
    return _parse_phone_response(resp_wrap.value)


@dataclass
class MyHomeEnrichReport:
    enriched: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class MyHomeEnricher:
    """Playwright-обогащение: детали со страницы + телефон из ответа phone/show."""

    def __init__(
        self,
        repository: LeadRepository,
        *,
        session_storage_path: Path,
        locale: str = "ru",
        headless: bool = True,
    ) -> None:
        self._repository = repository
        self._session_storage_path = session_storage_path
        self._locale = locale
        self._headless = headless

    def _ensure_session_file(self) -> None:
        if not self._session_storage_path.is_file():
            raise SessionExpiredError()

    def enrich_leads(self, leads: Iterable[Lead]) -> MyHomeEnrichReport:
        self._ensure_session_file()
        report = MyHomeEnrichReport()
        items = list(leads)
        if not items:
            return report

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self._headless)
            try:
                context = browser.new_context(
                    storage_state=str(self._session_storage_path),
                    locale=self._locale,
                )
                page = context.new_page()
                for lead in items:
                    err = self._enrich_one(page, lead)
                    if err is None:
                        report.enriched += 1
                    else:
                        report.failed += 1
                        report.errors.append(err)
            finally:
                browser.close()
        return report

    def _enrich_one(self, page: Page, lead: Lead) -> str | None:
        lid = str(lead.id) if lead.id else "none"
        label = f"id={lid} ext={lead.external_id}"
        try:
            if lead.id is None:
                return f"no_lead_id:{lead.external_id}"
            if lead.source_listing_uuid is None:
                return f"missing_uuid:{lead.external_id}"

            url = listing_url(lead.external_id, locale=self._locale)
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if _looks_like_login(page):
                raise SessionExpiredError()

            details = extract_details_from_page_text(_visible_text(page))
            phone = _click_show_phone(page)

            area_val = details.get("area_m2")
            area_dec: Decimal | None
            if isinstance(area_val, (int, float)):
                area_dec = Decimal(str(area_val))
            else:
                area_dec = None

            updated = lead.model_copy(
                update={
                    "phone": phone,
                    "address": details.get("address"),
                    "district": details.get("district"),
                    "area_m2": area_dec,
                    "rooms": details.get("rooms"),
                    "floor": details.get("floor"),
                    "description": details.get("description"),
                    "is_owner": bool(details.get("is_owner")),
                },
            )
            self._repository.update_enriched_fields(updated)
        except SessionExpiredError:
            logger.warning("myhome session expired (%s)", label)
            raise
        except Exception as exc:
            logger.warning(
                "myhome enrich fail %s type=%s",
                label,
                type(exc).__name__,
            )
            return f"{lead.external_id}:{type(exc).__name__}"
        return None


def _looks_like_login(page: Page) -> bool:
    u = page.url.lower()
    return "login" in u or "sign" in u or "auth" in u
