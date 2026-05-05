"""Выгрузка PDF карточки myhome.ge через Playwright ``page.pdf()`` (печать страницы).

Файл сохраняется локально в ``MYHOME_PDF_OUTPUT_DIR``; в БД пишется ``pdf_url``
(публичный префикс ``MYHOME_PDF_PUBLIC_BASE_URL`` или префикс ``local:`` для dev).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from domain.lead import Lead
from parsers.adapters.myhome.browser import dismiss_popup
from parsers.adapters.myhome.constants import TW_MS
from parsers.adapters.myhome.extract import listing_url
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)


@dataclass
class MyHomePdfEnrichReport:
    enriched: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def resolve_pdf_url(*, external_id: str, public_base: str | None) -> str:
    """Сформировать значение ``Lead.pdf_url`` без раскрытия локальных путей в проде."""
    name = f"{external_id}.pdf"
    if public_base:
        return f"{public_base.rstrip('/')}/{name}"
    return f"local:{name}"


def render_listing_pdf(page: Page, listing_url_str: str, dest_file: Path) -> None:
    """Открыть карточку и сохранить PDF через движок печати Chromium."""
    page.goto(listing_url_str, wait_until="domcontentloaded", timeout=TW_MS)
    page.wait_for_load_state("networkidle", timeout=TW_MS)
    dismiss_popup(page)
    page.wait_for_timeout(1500)
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    page.pdf(path=str(dest_file), format="A4", print_background=True)


class MyHomePdfEnricher:
    """Очередь PDF: лиды без ``pdf_url`` после детализации."""

    def __init__(
        self,
        repository: LeadRepository,
        *,
        locale: str = "ru",
        headless: bool = False,
        output_dir: Path,
        public_base_url: str | None = None,
    ) -> None:
        self._repository = repository
        self._locale = locale
        self._headless = headless
        self._output_dir = output_dir
        self._public_base_url = public_base_url

    def enrich_leads(self, leads: Iterable[Lead]) -> MyHomePdfEnrichReport:
        report = MyHomePdfEnrichReport()
        items = list(leads)
        if not items:
            return report

        with sync_playwright() as pw:
            if self._headless:
                logger.info(
                    "myhome pdf enricher: headless=True игнорируется (P1 — видимый браузер)",
                )
            browser = pw.chromium.launch(headless=False)
            try:
                context = browser.new_context(locale=self._locale)
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
            url = listing_url(lead.external_id, locale=self._locale)
            dest = self._output_dir / f"{lead.external_id}.pdf"
            render_listing_pdf(page, url, dest)
            pdf_ref = resolve_pdf_url(
                external_id=lead.external_id,
                public_base=self._public_base_url,
            )
            merged = lead.model_copy(update={"pdf_url": pdf_ref})
            self._repository.update_enriched_fields(merged)
        except Exception as exc:
            logger.warning(
                "myhome pdf enrich fail %s type=%s",
                label,
                type(exc).__name__,
            )
            return f"{lead.external_id}:{type(exc).__name__}"
        return None
