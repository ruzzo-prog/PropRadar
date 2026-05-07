"""Контракт HTTP для playwright-worker (без реального Playwright/БД в фоне)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from worker.main import app

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
    run.assert_called_once_with("phone")


def test_login_returns_202() -> None:
    with patch("worker.main._run_myhome_login_subprocess") as run:
        response = client.post("/login", json={"adapter": "myhome"})
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"
    run.assert_called_once()
