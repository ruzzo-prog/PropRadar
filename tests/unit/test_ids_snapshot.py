"""Unit tests for myhome IDs snapshot file service."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from api.ids_snapshot import (
    _FileLock,
    read_snapshot_file,
    snapshot_status,
    start_refresh,
)
from config.settings import Settings


@pytest.fixture
def snapshot_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    snap = tmp_path / "snapshot.json"
    lock = tmp_path / ".lock"
    monkeypatch.setenv("MYHOME_IDS_SNAPSHOT_PATH", str(snap))
    monkeypatch.setenv("MYHOME_IDS_SNAPSHOT_LOCK_PATH", str(lock))
    return Settings()


def test_read_missing_snapshot(snapshot_settings: Settings) -> None:
    data = read_snapshot_file(snapshot_settings)
    assert data["ready"] is False
    assert data["ids"] == []
    assert data["count"] == 0


def test_read_valid_snapshot(snapshot_settings: Settings) -> None:
    path = snapshot_settings.myhome_ids_snapshot_path
    path.write_text(
        json.dumps(
            {
                "ids": ["1", "2"],
                "fetched_at": "2026-05-17T10:00:00+00:00",
                "count": 2,
                "ready": True,
                "city": "tbilisi",
                "category": "apartment",
                "object_type": "apartment",
                "seller_type": "private",
                "pages_fetched": 3,
            },
        ),
        encoding="utf-8",
    )
    data = read_snapshot_file(snapshot_settings)
    assert data["ready"] is True
    assert data["count"] == 2
    assert data["ids"] == ["1", "2"]
    assert data["pages_fetched"] == 3


def test_snapshot_status_reflects_file(snapshot_settings: Settings) -> None:
    path = snapshot_settings.myhome_ids_snapshot_path
    path.write_text(
        json.dumps(
            {
                "ids": ["9"],
                "fetched_at": "2020-01-01T00:00:00+00:00",
                "ready": True,
                "city": "tbilisi",
                "category": "apartment",
                "object_type": "apartment",
                "seller_type": "private",
                "pages_fetched": 1,
            },
        ),
        encoding="utf-8",
    )
    st = snapshot_status(snapshot_settings)
    assert st["ready"] is True
    assert st["count"] == 1
    assert st["age_seconds"] is not None
    assert st["age_seconds"] > 86400


def test_refresh_writes_snapshot(
    snapshot_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_fetch(client, **kwargs):
        return (["100", "200"], 2)

    monkeypatch.setattr(
        "api.ids_snapshot.fetch_all_external_ids_with_pages_sync",
        _fake_fetch,
    )
    started, _msg = start_refresh(snapshot_settings)
    assert started is True
    import time

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        st = snapshot_status(snapshot_settings)
        if not st["refreshing"] and st["ready"]:
            break
        time.sleep(0.05)
    else:
        pytest.fail("refresh did not complete")

    data = read_snapshot_file(snapshot_settings)
    assert data["ids"] == ["100", "200"]
    assert data["pages_fetched"] == 2
    assert data["ready"] is True


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl file lock not used on Windows")
def test_file_lock_closes_fd_when_flock_fails(snapshot_settings: Settings) -> None:
    path = snapshot_settings.myhome_ids_snapshot_lock_path
    first = _FileLock(path)
    assert first.acquire() is True
    second = _FileLock(path)
    assert second.acquire() is False
    assert second._fh is None
    first.release()


def test_refresh_conflict_returns_not_started(
    snapshot_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.ids_snapshot as mod

    monkeypatch.setattr(mod, "_refreshing", True)
    started, msg = start_refresh(snapshot_settings)
    assert started is False
    assert "running" in msg.lower()


def test_start_refresh_allows_second_run_after_first_completes(
    snapshot_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_fetch(client, **kwargs):
        return (["1"], 1)

    monkeypatch.setattr(
        "api.ids_snapshot.fetch_all_external_ids_with_pages_sync",
        _fake_fetch,
    )
    import time

    assert start_refresh(snapshot_settings)[0] is True
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not snapshot_status(snapshot_settings)["refreshing"]:
            break
        time.sleep(0.05)
    else:
        pytest.fail("first refresh did not finish")

    started, msg = start_refresh(snapshot_settings)
    assert started is True, msg
    deadline2 = time.monotonic() + 5.0
    while time.monotonic() < deadline2:
        if not snapshot_status(snapshot_settings)["refreshing"]:
            break
        time.sleep(0.05)


def test_run_refresh_clears_refreshing_when_file_lock_fails(
    snapshot_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.ids_snapshot as mod

    monkeypatch.setattr(mod._FileLock, "acquire", lambda self: False)
    monkeypatch.setattr(mod, "_refreshing", True)
    mod._run_refresh(snapshot_settings, mod.SnapshotFilterParams())
    assert mod._refreshing is False
    st = snapshot_status(snapshot_settings)
    assert st["refreshing"] is False
    assert st["last_error"] == "refresh already running (file lock)"
