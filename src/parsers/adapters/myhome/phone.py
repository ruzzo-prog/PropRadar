"""Телефон объявления myhome.ge: Playwright-клик по UI и разбор ответа ``phone/show``.

На карточке подмешивается reCAPTCHA v3; токен и номер телефона в логи не пишутся.
Отдельный вход на сайт не обязателен для типичных объявлений физлиц — состояние браузера
опционально задаётся файлом ``MYHOME_PLAYWRIGHT_STORAGE`` (если задан и существует).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, Response, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright_stealth import Stealth

from config.settings import Settings
from domain.lead import Lead
from parsers.adapters.myhome.browser import dismiss_popup, save_timeout_shot
from parsers.adapters.myhome.constants import BTN_SELECTORS, TW_MS
from parsers.adapters.myhome.extract import listing_url
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

_PHONE_BTN_TEXT_RE = re.compile(r"\+?[0-9]{9,13}")

_MYHOME_PHONE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


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
        loc = page.locator(sel)
        n = loc.count()
        for i in range(n):
            cand = loc.nth(i)
            box = cand.bounding_box()
            if box is not None and box["width"] > 0 and box["height"] > 0:
                btn = cand
                logger.debug("phone_btn visible sel=%r nth=%s ext=%s", sel, i, external_id)
                break
        if btn is not None:
            break
    if btn is None:
        raise PWTimeoutError(f"phone button not in DOM ext={external_id}")

    with page.expect_response(
        lambda r: "phone/show" in r.url,
        timeout=tw,
    ) as resp_info:
        handle = btn.element_handle(timeout=tw)
        if handle is None:
            raise PWTimeoutError(f"phone button no element_handle ext={external_id}")
        page.evaluate("el => el.click()", handle)
    response = resp_info.value
    if response.status == 204:
        page.wait_for_timeout(1000)
        text = btn.inner_text()
        m = _PHONE_BTN_TEXT_RE.search(text)
        if not m:
            raise RuntimeError("phone_btn_digits_missing")
        return m.group(0)
    return parse_phone_response(response)


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

        app_settings = Settings()
        launch_proxy = None
        if app_settings.playwright_proxy_server:
            launch_proxy = {"server": app_settings.playwright_proxy_server}
            if app_settings.playwright_proxy_user is not None:
                launch_proxy["username"] = app_settings.playwright_proxy_user
            if app_settings.playwright_proxy_pass is not None:
                launch_proxy["password"] = app_settings.playwright_proxy_pass

        with sync_playwright() as pw:
            launch_kw: dict = {
                "headless": self._headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if launch_proxy is not None:
                launch_kw["proxy"] = launch_proxy
            browser = pw.chromium.launch(**launch_kw)
            try:
                context = browser.new_context(
                    locale=self._locale,
                    storage_state=storage,
                    user_agent=_MYHOME_PHONE_USER_AGENT,
                )
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
            if "Just a moment" in page.title() or "Turnstile" in page.content():
                logger.warning("cloudflare_block ext=%s", lead.external_id)
                save_timeout_shot(page, lead)
                return "CloudflareBlock"
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
