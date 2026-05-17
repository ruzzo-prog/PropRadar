"""Файловый снапшот external_id myhome для n8n (без блокирующего fetch-ids)."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config.settings import Settings
from parsers.adapters.myhome.list_ids import (
    fetch_all_external_ids_with_pages_sync,
    list_httpx_client_kwargs,
)

logger = logging.getLogger(__name__)

DEFAULT_CITY = "tbilisi"
DEFAULT_CATEGORY = "apartment"
DEFAULT_OBJECT_TYPE = "apartment"
DEFAULT_SELLER_TYPE = "private"
DEFAULT_MAX_PAGES = 500

_refresh_state_lock = threading.Lock()
_refreshing = False
_last_error: str | None = None


@dataclass(frozen=True)
class SnapshotFilterParams:
    city: str = DEFAULT_CITY
    category: str = DEFAULT_CATEGORY
    object_type: str = DEFAULT_OBJECT_TYPE
    seller_type: str = DEFAULT_SELLER_TYPE
    max_pages: int = DEFAULT_MAX_PAGES


def snapshot_path(settings: Settings) -> Path:
    return settings.myhome_ids_snapshot_path.expanduser().resolve()


def lock_path(settings: Settings) -> Path:
    return settings.myhome_ids_snapshot_lock_path.expanduser().resolve()


def _parse_fetched_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_seconds(fetched_at: str | None) -> int | None:
    dt = _parse_fetched_at(fetched_at)
    if dt is None:
        return None
    return max(0, int((datetime.now(UTC) - dt).total_seconds()))


def _empty_payload(*, ready: bool = False) -> dict[str, Any]:
    return {
        "ids": [],
        "fetched_at": None,
        "count": 0,
        "ready": ready,
        "city": DEFAULT_CITY,
        "category": DEFAULT_CATEGORY,
        "object_type": DEFAULT_OBJECT_TYPE,
        "seller_type": DEFAULT_SELLER_TYPE,
        "pages_fetched": 0,
    }


def read_snapshot_file(settings: Settings) -> dict[str, Any]:
    path = snapshot_path(settings)
    if not path.is_file():
        return _empty_payload(ready=False)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Invalid snapshot file %s: %s", path, exc)
        return _empty_payload(ready=False)
    if not isinstance(data, dict):
        return _empty_payload(ready=False)
    ids = data.get("ids")
    if not isinstance(ids, list):
        ids = []
    ids_norm = [str(x).strip() for x in ids if x is not None]
    ids_norm = [x for x in ids_norm if x]
    fetched_at = data.get("fetched_at")
    if fetched_at is not None and not isinstance(fetched_at, str):
        fetched_at = None
    ready = bool(data.get("ready")) and bool(ids_norm) and fetched_at is not None
    return {
        "ids": ids_norm,
        "fetched_at": fetched_at,
        "count": len(ids_norm),
        "ready": ready,
        "city": data.get("city") if isinstance(data.get("city"), str) else DEFAULT_CITY,
        "category": data.get("category")
        if isinstance(data.get("category"), str)
        else DEFAULT_CATEGORY,
        "object_type": data.get("object_type")
        if isinstance(data.get("object_type"), str)
        else DEFAULT_OBJECT_TYPE,
        "seller_type": data.get("seller_type")
        if isinstance(data.get("seller_type"), str)
        else DEFAULT_SELLER_TYPE,
        "pages_fetched": int(data.get("pages_fetched") or 0),
    }


def snapshot_status(settings: Settings) -> dict[str, Any]:
    global _refreshing, _last_error  # noqa: PLW0603
    payload = read_snapshot_file(settings)
    with _refresh_state_lock:
        refreshing = _refreshing
        last_error = _last_error
    fetched_at = payload.get("fetched_at")
    return {
        "ready": payload.get("ready", False),
        "count": payload.get("count", 0),
        "fetched_at": fetched_at,
        "age_seconds": _age_seconds(fetched_at if isinstance(fetched_at, str) else None),
        "refreshing": refreshing,
        "last_error": last_error,
        "city": payload.get("city"),
        "category": payload.get("category"),
        "seller_type": payload.get("seller_type"),
        "object_type": payload.get("object_type"),
        "pages_fetched": payload.get("pages_fetched", 0),
    }


class _FileLock:
    """Неперекрывающийся lock refresh (fcntl на Linux, иначе no-op)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh: Any = None

    def acquire(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "a+b")  # noqa: SIM115
        if sys.platform == "win32":
            return True
        import fcntl

        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            self._fh = None
            return False
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        if sys.platform != "win32":
            import fcntl

            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        self._fh.close()
        self._fh = None


def _write_snapshot_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _run_refresh(settings: Settings, params: SnapshotFilterParams) -> None:
    global _refreshing, _last_error  # noqa: PLW0603
    file_lock = _FileLock(lock_path(settings))
    try:
        if not file_lock.acquire():
            with _refresh_state_lock:
                _last_error = "refresh already running (file lock)"
            return

        base_url = str(settings.myhome_api_base_url).rstrip("/")
        with httpx.Client(**list_httpx_client_kwargs(settings)) as client:
            ids, pages_fetched = fetch_all_external_ids_with_pages_sync(
                client,
                base_url=base_url,
                max_pages=params.max_pages,
                limit=None,
                city=params.city,
                category=params.category,
                object_type=params.object_type,
                seller_type=params.seller_type,
            )
        fetched_at = datetime.now(UTC).isoformat()
        payload = {
            "ids": ids,
            "fetched_at": fetched_at,
            "count": len(ids),
            "ready": True,
            "city": params.city,
            "category": params.category,
            "object_type": params.object_type,
            "seller_type": params.seller_type,
            "pages_fetched": pages_fetched,
        }
        _write_snapshot_atomic(snapshot_path(settings), payload)
        with _refresh_state_lock:
            _last_error = None
        logger.info(
            "ids_snapshot refresh done count=%s pages=%s",
            len(ids),
            pages_fetched,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ids_snapshot refresh failed")
        with _refresh_state_lock:
            _last_error = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        file_lock.release()
        with _refresh_state_lock:
            _refreshing = False


def start_refresh(settings: Settings, params: SnapshotFilterParams | None = None) -> tuple[bool, str]:
    """Запустить фоновый refresh. Возвращает (started, message)."""
    global _refreshing, _last_error  # noqa: PLW0603
    filt = params or SnapshotFilterParams()
    with _refresh_state_lock:
        if _refreshing:
            return False, "refresh already running"
        _refreshing = True
        _last_error = None

    def _target() -> None:
        _run_refresh(settings, filt)

    threading.Thread(target=_target, name="myhome-ids-snapshot-refresh", daemon=True).start()
    return True, "refresh started"
