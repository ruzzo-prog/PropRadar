"""HTTP API /api/myhome: auth и обёртка subprocess (моки)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def dev_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("PROPRADAR_API_KEY", raising=False)


def test_health_unauthenticated() -> None:
    r = TestClient(app).get("/health")
    assert r.status_code == 200


def test_myhome_forbidden_in_prod_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROPRADAR_API_KEY", "secret")
    client = TestClient(app)
    assert client.get("/api/myhome/fetch-ids").status_code == 403


def test_myhome_prod_blocks_when_server_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("PROPRADAR_API_KEY", raising=False)
    client = TestClient(app)
    assert client.get("/api/myhome/fetch-ids", headers={"X-API-Key": "any"}).status_code == 403


def test_myhome_prod_ok_with_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROPRADAR_API_KEY", "secret")

    captured: dict[str, object] = {}

    def _fake_fetch(client, **kwargs):
        captured.update(kwargs)
        return ["10"]

    monkeypatch.setattr("api.myhome.fetch_all_external_ids_sync", _fake_fetch)
    client = TestClient(app)
    r = client.get("/api/myhome/fetch-ids", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    assert r.json() == ["10"]
    assert captured["city"] == "tbilisi"
    assert captured["category"] == "apartment"
    assert captured["object_type"] == "apartment"
    assert captured["seller_type"] == "private"
    assert captured["limit"] is None


def test_dev_allows_without_key_when_unset(
    dev_no_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_fetch(client, **kwargs):
        return []

    monkeypatch.setattr("api.myhome.fetch_all_external_ids_sync", _fake_fetch)
    r = TestClient(app).get("/api/myhome/fetch-ids")
    assert r.status_code == 200


def test_fetch_ids_passes_custom_filters(dev_no_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_fetch(client, **kwargs):
        captured.update(kwargs)
        return ["42"]

    monkeypatch.setattr("api.myhome.fetch_all_external_ids_sync", _fake_fetch)
    r = TestClient(app).get(
        "/api/myhome/fetch-ids?city=tbilisi&category=apartment&object_type=apartment&seller_type=private&limit=100"
    )
    assert r.status_code == 200
    assert r.json() == ["42"]
    assert captured["limit"] == 100
    assert captured["city"] == "tbilisi"
    assert captured["category"] == "apartment"
    assert captured["object_type"] == "apartment"
    assert captured["seller_type"] == "private"


def test_fetch_ids_returns_400_for_unsupported_filter(
    dev_no_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_fetch(client, **kwargs):
        raise ValueError("Unsupported city: batumi")

    monkeypatch.setattr("api.myhome.fetch_all_external_ids_sync", _fake_fetch)
    r = TestClient(app).get("/api/myhome/fetch-ids?city=batumi")
    assert r.status_code == 400


def test_fetch_ids_returns_400_for_unsupported_object_type(
    dev_no_key: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_fetch(client, **kwargs):
        raise ValueError("Unsupported object_type: house")

    monkeypatch.setattr("api.myhome.fetch_all_external_ids_sync", _fake_fetch)
    r = TestClient(app).get("/api/myhome/fetch-ids?object_type=house")
    assert r.status_code == 400


def test_fetch_ids_returns_400_for_invalid_limit(
    dev_no_key: None,
) -> None:
    r = TestClient(app).get("/api/myhome/fetch-ids?limit=abc")
    assert r.status_code == 400


def test_dev_rejects_mismatched_key_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PROPRADAR_API_KEY", "good")
    r = TestClient(app).get("/api/myhome/fetch-ids", headers={"X-API-Key": "bad"})
    assert r.status_code == 403


def test_ingest_empty_ids(dev_no_key: None) -> None:
    r = TestClient(app).post("/api/myhome/ingest", json={"ids": []})
    assert r.status_code == 200
    assert r.json() == {"parsed": 0, "new": 0, "errors": []}


def test_ingest_calls_cli(dev_no_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(settings, script: str, args: list[str]) -> tuple[int, str, str]:
        assert script == "run_myhome_parser.py"
        assert "--ingest-ids-json" in args
        return 0, '{"parsed":2,"new":1,"errors":[]}', ""

    monkeypatch.setattr("api.myhome._run_cli", _fake_run)
    r = TestClient(app).post("/api/myhome/ingest", json={"ids": [1, "2"]})
    assert r.status_code == 200
    assert r.json()["new"] == 1


def test_sync_status(dev_no_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = '{"disappeared":[],"counts":{"api_ids":0,"db_new_external_ids":0,"disappeared":0}}'

    def _fake_run(settings, script: str, args: list[str]) -> tuple[int, str, str]:
        assert "discover" in args and "--fetch-api" in args
        return 0, payload, ""

    monkeypatch.setattr("api.myhome._run_cli", _fake_run)
    r = TestClient(app).post("/api/myhome/sync-status")
    assert r.status_code == 200
    assert r.json()["counts"]["disappeared"] == 0


def test_mark_rejected(dev_no_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(settings, script: str, args: list[str]) -> tuple[int, str, str]:
        assert "mark-rejected" in args
        return 0, '{"updated":1,"reason":"disappeared_from_api"}', ""

    monkeypatch.setattr("api.myhome._run_cli", _fake_run)
    r = TestClient(app).post(
        "/api/myhome/mark-rejected",
        json={"ids": ["99"], "reason": "disappeared_from_api"},
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1
