"""Пакетное обогащение myhome.ge: API-детали → телефон (HTTP 2captcha) → PDF; JSON в stdout."""

from __future__ import annotations

import json
import logging
import sys

import httpx
from sqlalchemy import text

from config.settings import Settings
from parsers.adapters.myhome.enricher import MyHomeEnricher
from parsers.adapters.myhome.pdf import MyHomePdfEnricher
from parsers.adapters.myhome.phone import MyHomePhoneEnricher
from parsers.adapters.myhome.phone_http import MyHomePhoneHttpEnricher
from parsers.myhome import MyHomeParser
from repositories.postgres_lead_repository import (
    PostgresLeadRepository,
    PostgresSessionFactory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("run_myhome_enricher")


def _ping_db(sessions: PostgresSessionFactory) -> None:
    with sessions.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def main() -> int:
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    limit = settings.myhome_enrich_limit
    src = MyHomeParser.SOURCE

    leads_detail = repo.list_pending_detail_enrichment(src, limit=limit)
    with httpx.Client() as http_client:
        detail_enricher = MyHomeEnricher(
            repo,
            base_url=str(settings.myhome_api_base_url),
            client=http_client,
        )
        report_detail = detail_enricher.enrich_leads(leads_detail)

    phone_http_summary = {
        "phone_http_enriched": 0,
        "phone_http_failed": 0,
        "phone_http_errors": [],
    }
    phone_playwright_summary = {
        "phone_playwright_enriched": 0,
        "phone_playwright_failed": 0,
        "phone_playwright_errors": [],
    }

    if settings.myhome_phone_http_enabled and settings.twocaptcha_api_key:
        http_enricher = MyHomePhoneHttpEnricher(
            repo,
            base_url=str(settings.myhome_api_base_url),
            session_path=settings.myhome_session_path,
            twocaptcha_api_key=settings.twocaptcha_api_key,
            recaptcha_site_key=settings.myhome_recaptcha_site_key,
            max_workers=settings.myhome_phone_http_workers,
        )
        report_http = http_enricher.enrich_batch(src, limit=limit)
        phone_http_summary = {
            "phone_http_enriched": report_http.enriched,
            "phone_http_failed": report_http.failed,
            "phone_http_errors": report_http.errors,
        }
    else:
        phone_http_summary["phone_http_errors"] = ["http_disabled_or_no_twocaptcha_key"]

    if settings.myhome_phone_playwright_fallback:
        leads_phone = repo.claim_pending_phone_enrichment(src, limit=limit)
        phone_enricher = MyHomePhoneEnricher(
            repo,
            headless=True,
            storage_state_path=settings.myhome_session_path,
        )
        report_phone = phone_enricher.enrich_leads(leads_phone)
        phone_playwright_summary = {
            "phone_playwright_enriched": report_phone.enriched,
            "phone_playwright_failed": report_phone.failed,
            "phone_playwright_errors": report_phone.errors,
        }

    phone_enriched = (
        phone_http_summary["phone_http_enriched"]
        + phone_playwright_summary["phone_playwright_enriched"]
    )
    phone_failed = (
        phone_http_summary["phone_http_failed"]
        + phone_playwright_summary["phone_playwright_failed"]
    )
    phone_errors = [
        *phone_http_summary["phone_http_errors"],
        *phone_playwright_summary["phone_playwright_errors"],
    ]

    leads_pdf = repo.list_pending_pdf_enrichment(src, limit=limit)
    pdf_enricher = MyHomePdfEnricher(
        repo,
        headless=True,
        output_dir=settings.myhome_pdf_output_dir,
        public_base_url=settings.myhome_pdf_public_base_url,
    )
    report_pdf = pdf_enricher.enrich_leads(leads_pdf)

    print(
        json.dumps(
            {
                "detail_enriched": report_detail.enriched,
                "detail_failed": report_detail.failed,
                "detail_errors": report_detail.errors,
                **phone_http_summary,
                **phone_playwright_summary,
                "phone_enriched": phone_enriched,
                "phone_failed": phone_failed,
                "phone_errors": phone_errors,
                "pdf_enriched": report_pdf.enriched,
                "pdf_failed": report_pdf.failed,
                "pdf_errors": report_pdf.errors,
            },
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        logger.error("Fatal: %s", type(exc).__name__)
        print(
            json.dumps(
                {
                    "detail_enriched": 0,
                    "detail_failed": 0,
                    "detail_errors": [],
                    "phone_http_enriched": 0,
                    "phone_http_failed": 0,
                    "phone_http_errors": [],
                    "phone_playwright_enriched": 0,
                    "phone_playwright_failed": 0,
                    "phone_playwright_errors": [],
                    "phone_enriched": 0,
                    "phone_failed": 0,
                    "phone_errors": [],
                    "pdf_enriched": 0,
                    "pdf_failed": 0,
                    "pdf_errors": [],
                    "fatal": type(exc).__name__,
                },
                ensure_ascii=False,
            ),
        )
        sys.exit(1)
