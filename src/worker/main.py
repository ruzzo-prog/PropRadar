"""FastAPI worker: фоновой enrich и опциональный login для адаптеров с Playwright."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from config.settings import Settings
from parsers.adapters.myhome.enricher import MyHomeEnricher
from parsers.adapters.myhome.pdf import MyHomePdfEnricher
from parsers.adapters.myhome.phone import MyHomePhoneEnricher
from parsers.adapters.myhome.phone_http import (
    MyHomePhoneHttpEnricher,
    session_needs_login,
)
from parsers.myhome import MyHomeParser
from repositories.postgres_lead_repository import (
    PostgresLeadRepository,
    PostgresSessionFactory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("playwright_worker")

app = FastAPI(title="PropRadar Playwright Worker", version="0.2.0")

_job_lock = Lock()
_DEFAULT_SESSION_MIN_REMAINING_S = 40.0


class EnrichRequest(BaseModel):
    adapter: Literal["myhome"] = Field(description="Идентификатор адаптера")
    phase: Literal["detail", "phone", "phone_playwright", "pdf"] = Field(
        description="Фаза обогащения",
    )
    limit: int | None = Field(default=None, description="Размер батча; иначе MYHOME_ENRICH_LIMIT")


class LoginRequest(BaseModel):
    adapter: Literal["myhome"] = Field(description="Идентификатор адаптера")


def _repo_root() -> Path:
    env = Settings().propradar_repo_root
    if env is not None:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def _session_min_remaining_seconds() -> float:
    raw = os.getenv("MYHOME_SESSION_MIN_REMAINING_SECONDS", "40")
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "invalid MYHOME_SESSION_MIN_REMAINING_SECONDS=%r, using default %.0f",
            raw,
            _DEFAULT_SESSION_MIN_REMAINING_S,
        )
        return _DEFAULT_SESSION_MIN_REMAINING_S


def _ping_db(sessions: PostgresSessionFactory) -> None:
    with sessions.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _run_myhome_phone_http(
    repo: PostgresLeadRepository,
    settings: Settings,
    limit: int,
) -> dict[str, object]:
    if not settings.myhome_phone_http_enabled:
        return {
            "phone_http_enriched": 0,
            "phone_http_failed": 0,
            "phone_http_errors": ["http_disabled"],
        }
    api_key = settings.twocaptcha_api_key
    if not api_key:
        return {
            "phone_http_enriched": 0,
            "phone_http_failed": 0,
            "phone_http_errors": ["twocaptcha_api_key_missing"],
        }
    # Параллелизм phone HTTP — внутри enricher (claim 1 лид / задача пула); _job_lock — один job на контейнер.
    enricher = MyHomePhoneHttpEnricher(
        repo,
        base_url=str(settings.myhome_api_base_url),
        session_path=settings.myhome_session_path,
        twocaptcha_api_key=api_key,
        recaptcha_site_key=settings.myhome_recaptcha_site_key,
        max_workers=settings.myhome_phone_http_workers,
    )
    report = enricher.enrich_batch(MyHomeParser.SOURCE, limit=limit)
    return {
        "phone_http_enriched": report.enriched,
        "phone_http_failed": report.failed,
        "phone_http_errors": report.errors,
    }


def _run_myhome_phone_playwright(
    repo: PostgresLeadRepository,
    settings: Settings,
    limit: int,
) -> dict[str, object]:
    leads_phone = repo.claim_pending_phone_enrichment(MyHomeParser.SOURCE, limit=limit)
    phone_enricher = MyHomePhoneEnricher(
        repo,
        headless=True,
        storage_state_path=settings.myhome_session_path,
    )
    report = phone_enricher.enrich_leads(leads_phone)
    return {
        "phone_playwright_enriched": report.enriched,
        "phone_playwright_failed": report.failed,
        "phone_playwright_errors": report.errors,
    }


def _run_myhome_enrich_phase(phase: str, *, override_limit: int | None = None) -> None:
    """Синхронный прогон одной фазы (как run_myhome_enricher, лимиты те же)."""
    settings = Settings()
    sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
    _ping_db(sessions)
    repo = PostgresLeadRepository(sessions)
    limit = override_limit or settings.myhome_enrich_limit
    src = MyHomeParser.SOURCE
    summary: dict[str, object] = {"adapter": "myhome", "phase": phase}

    if phase == "detail":
        leads_detail = repo.list_pending_detail_enrichment(src, limit=limit)
        with httpx.Client() as http_client:
            detail_enricher = MyHomeEnricher(
                repo,
                base_url=str(settings.myhome_api_base_url),
                client=http_client,
            )
            report = detail_enricher.enrich_leads(leads_detail)
        summary.update(
            {
                "detail_enriched": report.enriched,
                "detail_failed": report.failed,
                "detail_errors": report.errors,
            },
        )
    elif phase == "phone":
        min_remaining = _session_min_remaining_seconds()
        if session_needs_login(settings.myhome_session_path, min_remaining=min_remaining):
            login_started = time.monotonic()
            login_code = _run_myhome_login_subprocess()
            if login_code != 0:
                login_err = f"login_failed_exit_{login_code}"
                summary.update(
                    {
                        "phone_http_enriched": 0,
                        "phone_http_failed": 0,
                        "phone_http_errors": [login_err],
                        "phone_enriched": 0,
                        "phone_failed": 0,
                        "phone_errors": [login_err],
                    },
                )
                logger.info("enrich done %s", json.dumps(summary, ensure_ascii=False))
                return
            logger.info(
                "myhome_login duration_s=%.1f",
                time.monotonic() - login_started,
            )
        summary.update(_run_myhome_phone_http(repo, settings, limit))
        summary.update(
            {
                "phone_enriched": summary.get("phone_http_enriched", 0),
                "phone_failed": summary.get("phone_http_failed", 0),
                "phone_errors": summary.get("phone_http_errors", []),
            },
        )
    elif phase == "phone_playwright":
        summary.update(_run_myhome_phone_playwright(repo, settings, limit))
        summary.update(
            {
                "phone_enriched": summary.get("phone_playwright_enriched", 0),
                "phone_failed": summary.get("phone_playwright_failed", 0),
                "phone_errors": summary.get("phone_playwright_errors", []),
            },
        )
    elif phase == "pdf":
        leads_pdf = repo.list_pending_pdf_enrichment(src, limit=limit)
        pdf_enricher = MyHomePdfEnricher(
            repo,
            headless=True,
            output_dir=settings.myhome_pdf_output_dir,
            public_base_url=settings.myhome_pdf_public_base_url,
        )
        report = pdf_enricher.enrich_leads(leads_pdf)
        summary.update(
            {
                "pdf_enriched": report.enriched,
                "pdf_failed": report.failed,
                "pdf_errors": report.errors,
            },
        )
    else:  # pragma: no cover
        raise ValueError(f"unknown phase: {phase}")

    logger.info("enrich done %s", json.dumps(summary, ensure_ascii=False))


def _run_myhome_login_subprocess() -> int:
    root = _repo_root()
    script = root / "scripts" / "myhome_login.py"
    if not script.is_file():
        logger.error("myhome_login script not found: %s", script)
        return 1
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        env=env,
        check=False,
    )
    logger.info("myhome_login exit_code=%s", proc.returncode)
    return int(proc.returncode)


def _locked_background(sync_fn: Callable[[], None]) -> None:
    """Один фоновой job за раз (Playwright + БД)."""
    if not _job_lock.acquire(blocking=False):
        logger.warning("background job skipped: another job is running")
        return
    try:
        sync_fn()
    finally:
        _job_lock.release()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/enrich", status_code=202)
async def enrich(
    body: EnrichRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if body.adapter != "myhome":
        raise HTTPException(status_code=400, detail="unsupported adapter")
    phase = body.phase

    def job() -> None:
        _run_myhome_enrich_phase(phase, override_limit=body.limit)

    background_tasks.add_task(_locked_background, job)
    return {"status": "accepted", "adapter": body.adapter, "phase": body.phase}


@app.post("/login", status_code=202)
async def login(
    body: LoginRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if body.adapter != "myhome":
        raise HTTPException(status_code=400, detail="unsupported adapter")

    background_tasks.add_task(_locked_background, _run_myhome_login_subprocess)
    return {"status": "accepted", "adapter": body.adapter}
