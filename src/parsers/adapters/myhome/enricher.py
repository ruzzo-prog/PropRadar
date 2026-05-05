"""Playwright-обогащение myhome: детали со страницы + телефон из ответа phone/show."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeoutError

from domain.lead import Lead
from parsers.adapters.myhome.browser import (
    click_show_phone,
    dismiss_popup,
    save_timeout_shot,
    visible_text,
)
from parsers.adapters.myhome.constants import TW_MS
from parsers.adapters.myhome.extract import extract_details_from_page_text, listing_url
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)


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
        locale: str = "ru",
        headless: bool = False,
    ) -> None:
        self._repository = repository
        self._locale = locale
        self._headless = headless

    def enrich_leads(self, leads: Iterable[Lead]) -> MyHomeEnrichReport:
        report = MyHomeEnrichReport()
        items = list(leads)
        if not items:
            return report

        with sync_playwright() as pw:
            if self._headless:
                logger.info("myhome enricher: headless=True игнорируется (P1 — видимый браузер)")
            browser = pw.chromium.launch(headless=False)
            try:
                session_path = Path("scripts/myhome_session.json")
                storage = (
                    json.loads(session_path.read_text(encoding="utf-8"))
                    if session_path.exists()
                    else None
                )
                context = browser.new_context(
                    locale=self._locale,
                    storage_state=storage,
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
        label = f"source=myhome id={lid} ext={lead.external_id}"
        try:
            if lead.id is None:
                return f"no_lead_id:{lead.external_id}"
            if lead.source_listing_uuid is None:
                return f"missing_uuid:{lead.external_id}"

            url = listing_url(lead.external_id, locale=self._locale)
            page.goto(url, wait_until="domcontentloaded", timeout=TW_MS)
            page.wait_for_load_state("networkidle", timeout=TW_MS)

            dismiss_popup(page)
            page.wait_for_timeout(3000)

            html_lang: str | None = None
            try:
                raw_lang = page.locator("html").first.get_attribute("lang")
                if raw_lang:
                    html_lang = raw_lang.strip()
            except Exception:
                pass

            text = visible_text(page)
            details = extract_details_from_page_text(
                text,
                listing_url=url,
                html_lang=html_lang,
            )
            phone = click_show_phone(page, lead.external_id)

            update: dict[str, object] = {"phone": phone}

            area_val = details.get("area_m2")
            if isinstance(area_val, (int, float)):
                update["area_m2"] = Decimal(str(area_val))

            if (v := details.get("rooms")) is not None:
                update["rooms"] = v
            if (v := details.get("floor")) is not None:
                update["floor"] = v

            for key in (
                "address",
                "district",
                "description",
                "published_at",
                "address_lang",
                "district_lang",
                "description_lang",
            ):
                if (val := details.get(key)) is not None:
                    update[key] = val

            if details.get("is_owner") is True:
                update["is_owner"] = True

            updated = lead.model_copy(update=update)
            self._repository.update_enriched_fields(updated)
        except PWTimeoutError:
            save_timeout_shot(page, lead)
            logger.warning("myhome enrich fail %s type=TimeoutError", label)
            return f"{lead.external_id}:TimeoutError"
        except Exception as exc:
            logger.warning(
                "myhome enrich fail %s type=%s",
                label,
                type(exc).__name__,
            )
            if type(exc).__name__ == "TimeoutError":
                save_timeout_shot(page, lead)
            return f"{lead.external_id}:{type(exc).__name__}"
        return None
