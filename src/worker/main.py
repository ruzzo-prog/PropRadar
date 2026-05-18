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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from config.settings import Settings
from parsers.adapters.myhome.enricher import MyHomeEnricher
from parsers.adapters.myhome.pdf import MyHomePdfEnricher
from parsers.adapters.myhome.phone import MyHomePhoneEnricher
from parsers.adapters.myhome.phone_http import (
    MyHomePhoneHttpEnricher,
    access_token_expires_at_iso,
    access_token_remaining_seconds,
    httpx_client_kwargs_from_settings,
    httpx_proxy_from_settings,
    session_needs_login,
)
from parsers.myhome import MyHomeParser
from repositories.postgres_lead_repository import (
    PostgresLeadRepository,
    PostgresSessionFactory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("playwright_worker")

app = FastAPI(title="PropRadar Playwright Worker", version="0.3.0")

_job_lock = Lock()
_metrics_lock = Lock()
_job_status_lock = Lock()
_metrics: dict[str, int] = {
    "total_enriched": 0,
    "total_failed": 0,
    "total_401": 0,
    "total_logins": 0,
}
_job_status: dict[str, str | float | None] = {
    "job": None,
    "started_monotonic": None,
}
_last_enrich_result: dict[str, object] | None = None
_last_enrich_lock = Lock()
_DEFAULT_SESSION_MIN_REMAINING_S = 40.0
_PROXY_CHECK_URL = "https://api.ipify.org?format=json"
_PROXY_CHECK_TIMEOUT_S = 15.0
_QUEUE_PENDING_SQL = text(
    """
    SELECT COUNT(*)::int AS pending
    FROM leads
    WHERE source = 'myhome'
      AND status = 'new'
      AND (phone IS NULL OR phone = '')
      AND phone_retries < 3
    """,
)


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


def _sanitize_error(exc: BaseException) -> str:
    name = type(exc).__name__
    msg = str(exc).strip()
    if not msg:
        return name
    if "://" in msg and "@" in msg:
        return name
    return f"{name}: {msg[:200]}"


def _record_login_success(exit_code: int) -> None:
    if exit_code != 0:
        return
    with _metrics_lock:
        _metrics["total_logins"] += 1


def _record_phone_metrics(phone_summary: dict[str, object]) -> None:
    enriched = int(phone_summary.get("phone_http_enriched", 0) or 0)
    failed = int(phone_summary.get("phone_http_failed", 0) or 0)
    errors = phone_summary.get("phone_http_errors", [])
    unauthorized = 0
    if isinstance(errors, list):
        unauthorized = sum(1 for err in errors if err == "phone_api_unauthorized")
    with _metrics_lock:
        _metrics["total_enriched"] += enriched
        _metrics["total_failed"] += failed
        _metrics["total_401"] += unauthorized


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
        relogin_fn=_run_myhome_login_subprocess,
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
            _record_login_success(login_code)
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
                _finish_enrich(summary)
                return
            logger.info(
                "myhome_login duration_s=%.1f",
                time.monotonic() - login_started,
            )
        phone_summary = _run_myhome_phone_http(repo, settings, limit)
        _record_phone_metrics(phone_summary)
        summary.update(phone_summary)
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

    _finish_enrich(summary)


def _finish_enrich(summary: dict[str, object]) -> None:
    global _last_enrich_result
    logger.info("enrich done %s", json.dumps(summary, ensure_ascii=False))
    with _last_enrich_lock:
        _last_enrich_result = summary


def _run_myhome_login_subprocess(*, max_attempts: int = 3, retry_delay_s: float = 15.0) -> int:
    root = _repo_root()
    script = root / "scripts" / "myhome_login.py"
    if not script.is_file():
        logger.error("myhome_login script not found: %s", script)
        return 1
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    for attempt in range(1, max_attempts + 1):
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            env=env,
            check=False,
        )
        exit_code = int(proc.returncode)
        logger.info("myhome_login exit_code=%s attempt=%d/%d", exit_code, attempt, max_attempts)
        if exit_code == 0:
            return 0
        if attempt < max_attempts:
            logger.info("myhome_login retry in %.0fs", retry_delay_s)
            time.sleep(retry_delay_s)
    return 1


def _locked_background(sync_fn: Callable[[], None], *, job_name: str) -> None:
    """Один фоновой job за раз (Playwright + БД)."""
    if not _job_lock.acquire(blocking=False):
        logger.warning("background job skipped: another job is running")
        return
    with _job_status_lock:
        _job_status["job"] = job_name
        _job_status["started_monotonic"] = time.monotonic()
    try:
        sync_fn()
    finally:
        with _job_status_lock:
            _job_status["job"] = None
            _job_status["started_monotonic"] = None
        _job_lock.release()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/proxy/check", response_model=None)
def proxy_check() -> dict[str, object] | JSONResponse:
    settings = Settings()
    if not httpx_proxy_from_settings(settings):
        return {"ok": True, "skipped": True}
    try:
        client_kw = httpx_client_kwargs_from_settings(settings)
        client_kw["timeout"] = _PROXY_CHECK_TIMEOUT_S
        response = httpx.get(_PROXY_CHECK_URL, **client_kw)
        response.raise_for_status()
        payload = response.json()
        ip = payload.get("ip") if isinstance(payload, dict) else None
        if not ip:
            return JSONResponse(
                status_code=503,
                content={"ok": False, "reason": "ip_missing_in_response"},
            )
        return {"ok": True, "ip": str(ip)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"ok": False, "reason": _sanitize_error(exc)},
        )


@app.get("/session/check")
def session_check() -> dict[str, object]:
    settings = Settings()
    session_path = settings.myhome_session_path
    exists = session_path is not None and session_path.is_file()
    remaining = access_token_remaining_seconds(session_path)
    remaining_seconds: int | None = int(remaining) if remaining is not None else None
    expires_at = access_token_expires_at_iso(session_path)
    ok = exists and remaining is not None and remaining > 0
    return {
        "ok": ok,
        "exists": exists,
        "remaining_seconds": remaining_seconds,
        "expires_at": expires_at,
    }


@app.get("/status")
def worker_status() -> dict[str, object]:
    running = _job_lock.locked()
    with _job_status_lock:
        job = _job_status["job"]
        started = _job_status["started_monotonic"]
    elapsed: float | None = None
    if running and isinstance(started, (int, float)):
        elapsed = round(time.monotonic() - float(started), 3)
    with _last_enrich_lock:
        last_enrich = _last_enrich_result
    return {
        "status": "running" if running else "idle",
        "job": job if running else None,
        "elapsed_seconds": elapsed,
        "last_enrich": last_enrich,
    }


@app.post("/session/reset")
def session_reset() -> dict[str, object]:
    settings = Settings()
    session_path = settings.myhome_session_path
    if session_path is None or not session_path.is_file():
        return {"ok": False, "reason": "session_not_found"}
    try:
        session_path.unlink()
    except OSError:
        return {"ok": False, "reason": "unlink_failed"}
    return {"ok": True}


@app.get("/queue", response_model=None)
def queue_pending() -> dict[str, object] | JSONResponse:
    settings = Settings()
    try:
        sessions = PostgresSessionFactory.from_database_url(str(settings.database_url))
        with sessions.engine.connect() as conn:
            row = conn.execute(_QUEUE_PENDING_SQL).mappings().one()
        pending = int(row["pending"])
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"ok": False, "reason": "database_unavailable"},
        )
    return {"pending": pending}


@app.get("/metrics")
def worker_metrics() -> dict[str, int]:
    with _metrics_lock:
        return dict(_metrics)


@app.post("/enrich", status_code=202)
async def enrich(
    body: EnrichRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if body.adapter != "myhome":
        raise HTTPException(status_code=400, detail="unsupported adapter")
    phase = body.phase

    def enrich_job() -> None:
        _run_myhome_enrich_phase(phase, override_limit=body.limit)

    background_tasks.add_task(_locked_background, enrich_job, job_name=f"enrich:{phase}")
    return {"status": "accepted", "adapter": body.adapter, "phase": body.phase}


@app.post("/login", status_code=202)
async def login(
    body: LoginRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if body.adapter != "myhome":
        raise HTTPException(status_code=400, detail="unsupported adapter")

    def login_job() -> None:
        exit_code = _run_myhome_login_subprocess()
        _record_login_success(exit_code)

    background_tasks.add_task(_locked_background, login_job, job_name="login:myhome")
    return {"status": "accepted", "adapter": body.adapter}
