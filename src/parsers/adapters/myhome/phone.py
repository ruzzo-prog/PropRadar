"""Телефон объявления myhome.ge: Playwright-клик по UI и разбор ответа ``phone/show``.

На карточке подмешивается reCAPTCHA v3; токен и номер телефона в логи не пишутся.
Отдельный вход на сайт не обязателен для типичных объявлений физлиц — состояние браузера
опционально задаётся файлом ``MYHOME_PLAYWRIGHT_STORAGE`` (если задан и существует).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, Response, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright_stealth import Stealth

from domain.lead import Lead
from parsers.adapters.myhome.browser import dismiss_popup, save_timeout_shot
from parsers.adapters.myhome.constants import BTN_SELECTORS, TW_MS
from parsers.adapters.myhome.extract import listing_url
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)


def parse_phone_response(response: Response) -> str:
    """Разобрать JSON ответа телефона (HTTP статус и форма без логирования номера)."""
    if response.status == 401:
        raise RuntimeError("phone_api_unauthorized")
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


def click_show_phone(page: Page, external_id: str) -> str:
    """Нажать «показать номер», дождаться ``phone/show``, вернуть номер."""
    tw = 15_000
    btn = None
    for sel in BTN_SELECTORS:
        loc = page.locator(sel).first
        if loc.count() > 0:
            btn = loc
            logger.debug("phone_btn in_dom sel=%r ext=%s", sel, external_id)
            break
    if btn is None:
        raise PWTimeoutError(f"phone button not in DOM ext={external_id}")

    with page.expect_response(
        lambda r: "phone/show" in r.url and r.status == 200,
        timeout=tw,
    ) as resp_info:
        handle = btn.element_handle(timeout=tw)
        if handle is None:
            raise PWTimeoutError(f"phone button no element_handle ext={external_id}")
        page.evaluate("el => el.click()", handle)
    return parse_phone_response(resp_info.value)


@dataclass
class MyHomePhoneEnrichReport:
    enriched: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class MyHomePhoneEnricher:
    """Очередь телефона: только поле ``phone`` через Playwright."""

    def __init__(
        self,
        repository: LeadRepository,
        *,
        locale: str = "ru",
        headless: bool = True,
        storage_state_path: Path | None = None,
    ) -> None:
        self._repository = repository
        self._locale = locale
        self._headless = headless
        self._storage_state_path = storage_state_path

    def enrich_leads(self, leads: Iterable[Lead]) -> MyHomePhoneEnrichReport:
        report = MyHomePhoneEnrichReport()
        items = list(leads)
        if not items:
            return report

        storage = None
        if self._storage_state_path is not None and self._storage_state_path.exists():
            storage = json.loads(self._storage_state_path.read_text(encoding="utf-8"))

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self._headless)
            try:
                context = browser.new_context(locale=self._locale, storage_state=storage)
                page = context.new_page()
                Stealth().apply_stealth_sync(page)
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
        label = f"source=myhome id={lid} ext={lead.external_id}"
        try:
            if lead.id is None:
                return f"no_lead_id:{lead.external_id}"

            url = listing_url(lead.external_id, locale=self._locale)
            page.goto(url, wait_until="domcontentloaded", timeout=TW_MS)
            page.wait_for_load_state("networkidle", timeout=TW_MS)

            dismiss_popup(page)
            page.wait_for_timeout(3000)

            phone = click_show_phone(page, lead.external_id)
            merged = lead.model_copy(update={"phone": phone})
            self._repository.update_enriched_fields(merged)
        except PWTimeoutError:
            save_timeout_shot(page, lead)
            logger.warning("myhome phone enrich fail %s type=TimeoutError", label)
            return f"{lead.external_id}:TimeoutError"
        except Exception as exc:
            logger.warning(
                "myhome phone enrich fail %s type=%s",
                label,
                type(exc).__name__,
            )
            if type(exc).__name__ == "TimeoutError":
                save_timeout_shot(page, lead)
            return f"{lead.external_id}:{type(exc).__name__}"
        return None
