"""Контракт HTTP для playwright-worker (без реального Playwright/БД в фоне)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from worker.main import (
    _DEFAULT_SESSION_MIN_REMAINING_S,
    _run_myhome_enrich_phase,
    _session_min_remaining_seconds,
    app,
)

client = TestClient(app)


def test_worker_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_enrich_returns_202() -> None:
    with patch("worker.main._run_myhome_enrich_phase") as run:
        response = client.post("/enrich", json={"adapter": "myhome", "phase": "phone"})
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"
        assert body["adapter"] == "myhome"
        assert body["phase"] == "phone"
    run.assert_called_once_with("phone", override_limit=None)


def test_enrich_phone_playwright_phase_returns_202() -> None:
    with patch("worker.main._run_myhome_enrich_phase") as run:
        response = client.post(
            "/enrich",
            json={"adapter": "myhome", "phase": "phone_playwright"},
        )
        assert response.status_code == 202
        assert response.json()["phase"] == "phone_playwright"
    run.assert_called_once_with("phone_playwright", override_limit=None)


def test_enrich_passes_limit_to_phase() -> None:
    with patch("worker.main._run_myhome_enrich_phase") as run:
        response = client.post(
            "/enrich",
            json={"adapter": "myhome", "phase": "phone", "limit": 120},
        )
        assert response.status_code == 202
    run.assert_called_once_with("phone", override_limit=120)


def test_login_returns_202() -> None:
    with patch("worker.main._run_myhome_login_subprocess") as run:
        response = client.post("/login", json={"adapter": "myhome"})
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"
    run.assert_called_once()


def test_session_min_remaining_seconds_invalid_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYHOME_SESSION_MIN_REMAINING_SECONDS", "not-a-number")
    assert _session_min_remaining_seconds() == _DEFAULT_SESSION_MIN_REMAINING_S


def test_phone_phase_invalid_min_remaining_env_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYHOME_SESSION_MIN_REMAINING_SECONDS", "bad")
    settings = MagicMock()
    settings.database_url = "postgresql://test"
    settings.myhome_enrich_limit = 5
    settings.myhome_session_path = Path("/tmp/session.json")
    with (
        patch("worker.main.Settings", return_value=settings),
        patch("worker.main.PostgresSessionFactory"),
        patch("worker.main._ping_db"),
        patch("worker.main.PostgresLeadRepository"),
        patch("worker.main.session_needs_login", return_value=False) as needs,
        patch("worker.main._run_myhome_phone_http", return_value={}) as enrich,
    ):
        _run_myhome_enrich_phase("phone")
    needs.assert_called_once()
    assert needs.call_args.kwargs["min_remaining"] == _DEFAULT_SESSION_MIN_REMAINING_S
    enrich.assert_called_once()


def test_phone_phase_login_fail_skips_enrich() -> None:
    settings = MagicMock()
    settings.database_url = "postgresql://test"
    settings.myhome_enrich_limit = 5
    settings.myhome_session_path = Path("/tmp/session.json")
    with (
        patch("worker.main.Settings", return_value=settings),
        patch("worker.main.PostgresSessionFactory"),
        patch("worker.main._ping_db"),
        patch("worker.main.PostgresLeadRepository"),
        patch("worker.main.session_needs_login", return_value=True),
        patch("worker.main._run_myhome_login_subprocess", return_value=1) as login,
        patch("worker.main._run_myhome_phone_http") as enrich,
    ):
        _run_myhome_enrich_phase("phone")
    login.assert_called_once()
    enrich.assert_not_called()


def test_phone_phase_login_ok_runs_enrich() -> None:
    settings = MagicMock()
    settings.database_url = "postgresql://test"
    settings.myhome_enrich_limit = 5
    settings.myhome_session_path = Path("/tmp/session.json")
    enrich_summary = {
        "phone_http_enriched": 1,
        "phone_http_failed": 0,
        "phone_http_errors": [],
    }
    with (
        patch("worker.main.Settings", return_value=settings),
        patch("worker.main.PostgresSessionFactory"),
        patch("worker.main._ping_db"),
        patch("worker.main.PostgresLeadRepository"),
        patch("worker.main.session_needs_login", return_value=True),
        patch("worker.main._run_myhome_login_subprocess", return_value=0) as login,
        patch("worker.main._run_myhome_phone_http", return_value=enrich_summary) as enrich,
    ):
        _run_myhome_enrich_phase("phone")
    login.assert_called_once()
    enrich.assert_called_once()
