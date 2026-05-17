"""Контракт HTTP для playwright-worker (без реального Playwright/БД в фоне)."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from worker.main import (
    _DEFAULT_SESSION_MIN_REMAINING_S,
    _metrics,
    _metrics_lock,
    _record_phone_metrics,
    _run_myhome_enrich_phase,
    _sanitize_error,
    _session_min_remaining_seconds,
    app,
)

client = TestClient(app)


def _reset_metrics() -> None:
    with _metrics_lock:
        for key in _metrics:
            _metrics[key] = 0


def _session_with_token_expires(tmp_path: Path, expires_at: float) -> Path:
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .decode()
        .rstrip("=")
    )
    payload_segment = (
        base64.urlsafe_b64encode(json.dumps({"expires_at": expires_at}).encode())
        .decode()
        .rstrip("=")
    )
    token = f"{header}.{payload_segment}.sig"
    session = {"cookies": [{"name": "AccessToken", "value": token, "domain": ".tnet.ge"}]}
    path = tmp_path / "session.json"
    path.write_text(json.dumps(session), encoding="utf-8")
    return path


def test_worker_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_proxy_check_skipped_when_no_proxy() -> None:
    with patch("worker.main.httpx_proxy_from_settings", return_value=None):
        response = client.get("/proxy/check")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "skipped": True}


def test_proxy_check_ok() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"ip": "203.0.113.1"}
    with (
        patch("worker.main.httpx_proxy_from_settings", return_value="http://proxy.example:8080"),
        patch("worker.main.httpx.get", return_value=mock_response),
    ):
        response = client.get("/proxy/check")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "ip": "203.0.113.1"}


def test_proxy_check_failure_returns_503() -> None:
    with (
        patch("worker.main.httpx_proxy_from_settings", return_value="http://proxy.example:8080"),
        patch("worker.main.httpx.get", side_effect=httpx.ConnectError("connection refused")),
    ):
        response = client.get("/proxy/check")
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert "ConnectError" in body["reason"]


def test_session_check_valid_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_path = _session_with_token_expires(tmp_path, time.time() + 3600)
    settings = MagicMock()
    settings.myhome_session_path = session_path
    with patch("worker.main.Settings", return_value=settings):
        response = client.get("/session/check")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["exists"] is True
    assert body["remaining_seconds"] is not None
    assert body["expires_at"] is not None


def test_session_check_missing_file() -> None:
    settings = MagicMock()
    settings.myhome_session_path = Path("/nonexistent/session.json")
    with patch("worker.main.Settings", return_value=settings):
        response = client.get("/session/check")
    body = response.json()
    assert body["ok"] is False
    assert body["exists"] is False


def test_worker_status_idle() -> None:
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert body["job"] is None
    assert body["elapsed_seconds"] is None


def test_session_reset_ok(tmp_path: Path) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text("{}", encoding="utf-8")
    settings = MagicMock()
    settings.myhome_session_path = session_path
    with patch("worker.main.Settings", return_value=settings):
        response = client.post("/session/reset")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert not session_path.exists()


def test_session_reset_not_found() -> None:
    settings = MagicMock()
    settings.myhome_session_path = Path("/nonexistent/session.json")
    with patch("worker.main.Settings", return_value=settings):
        response = client.post("/session/reset")
    assert response.json() == {"ok": False, "reason": "session_not_found"}


def test_queue_pending() -> None:
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.one.return_value = {"pending": 7}
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    sessions = MagicMock()
    sessions.engine = engine
    settings = MagicMock()
    settings.database_url = "postgresql://test"
    with (
        patch("worker.main.Settings", return_value=settings),
        patch("worker.main.PostgresSessionFactory.from_database_url", return_value=sessions),
    ):
        response = client.get("/queue")
    assert response.status_code == 200
    assert response.json() == {"pending": 7}


def test_metrics_endpoint() -> None:
    _reset_metrics()
    _record_phone_metrics(
        {
            "phone_http_enriched": 2,
            "phone_http_failed": 1,
            "phone_http_errors": ["phone_api_unauthorized"],
        },
    )
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json() == {
        "total_enriched": 2,
        "total_failed": 1,
        "total_401": 1,
        "total_logins": 0,
    }


def test_sanitize_error_redacts_proxy_url() -> None:
    exc = httpx.ProxyError("502 Bad Gateway for url http://user:secret@proxy.example:8080")
    assert "secret" not in _sanitize_error(exc)
    assert _sanitize_error(exc) == "ProxyError"


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
    with patch("worker.main._locked_background") as locked:
        response = client.post(
            "/enrich",
            json={"adapter": "myhome", "phase": "phone", "limit": 120},
        )
        assert response.status_code == 202
    locked.assert_called_once()
    assert locked.call_args.kwargs["job_name"] == "enrich:phone"


def test_login_returns_202() -> None:
    with patch("worker.main._locked_background") as locked:
        response = client.post("/login", json={"adapter": "myhome"})
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"
    locked.assert_called_once()
    assert locked.call_args.kwargs["job_name"] == "login:myhome"


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
