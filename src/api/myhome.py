"""HTTP-адаптер к CLI myhome (subprocess к scripts/* без изменения скриптов)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config.settings import Settings

from .auth import get_settings, verify_propradar_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/myhome",
    tags=["myhome"],
    dependencies=[Depends(verify_propradar_api_key)],
)


def _repo_root(settings: Settings) -> Path:
    if settings.propradar_repo_root is not None:
        return settings.propradar_repo_root.expanduser().resolve()
    # src/api/myhome.py -> parents[2] == корень репозитория
    return Path(__file__).resolve().parents[2]


def _run_cli(
    settings: Settings,
    script: str,
    script_args: list[str],
) -> tuple[int, str, str]:
    root = _repo_root(settings)
    script_path = root / "scripts" / script
    if not script_path.is_file():
        msg = f"Скрипт не найден: {script_path}"
        raise HTTPException(status_code=503, detail=msg)
    cmd = [sys.executable, str(script_path), *script_args]
    env = {**os.environ, "PYTHONPATH": "src"}
    try:
        completed = subprocess.run(  # noqa: S603 — argv из кода, не из пользователя
            cmd,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=settings.myhome_cli_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("CLI timeout: %s", script)
        raise HTTPException(
            status_code=504,
            detail=f"Subprocess timeout after {settings.myhome_cli_timeout_seconds}s",
        ) from exc
    return completed.returncode, completed.stdout, completed.stderr


def _parse_json_stdout(stdout: str, *, script: str) -> Any:
    text = stdout.strip()
    if not text:
        raise HTTPException(status_code=502, detail=f"Empty stdout from {script}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON from %s: %s", script, text[:500])
        raise HTTPException(
            status_code=502,
            detail=f"Invalid JSON from {script}",
        ) from exc


@router.get("/fetch-ids")
def fetch_ids(
    settings: Annotated[Settings, Depends(get_settings)],
    since_days: int = Query(7, ge=1, le=3650),
    full: bool = Query(
        False,
        description="Полный список ID (--full), взаимоисключающе с since_days",
    ),
    max_pages: int = Query(500, ge=1, le=10_000),
) -> list[Any]:
    if full:
        args = ["--full", "--output", "json", "--max-pages", str(max_pages)]
    else:
        args = ["--since-days", str(since_days), "--output", "json", "--max-pages", str(max_pages)]
    code, out, err = _run_cli(settings, "fetch_myhome_ids.py", args)
    data = _parse_json_stdout(out, script="fetch_myhome_ids.py")
    if code != 0:
        logger.warning("fetch_myhome_ids exit=%s stderr=%s", code, err[-2000:] if err else "")
        raise HTTPException(
            status_code=502,
            detail={"exit_code": code, "stderr_tail": (err or "")[-2000:]},
        )
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Expected JSON array of IDs")
    return data


class IngestRequest(BaseModel):
    ids: list[int | str] = Field(default_factory=list)


@router.post("/ingest")
def ingest(
    body: IngestRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    if not body.ids:
        return {"parsed": 0, "new": 0, "errors": []}
    ids_normalized = [str(x).strip() for x in body.ids if x is not None]
    ids_normalized = [x for x in ids_normalized if x]
    if not ids_normalized:
        return {"parsed": 0, "new": 0, "errors": []}
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(ids_normalized, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name).resolve()
    arg_path = str(tmp_path)
    try:
        code, out, err = _run_cli(
            settings,
            "run_myhome_parser.py",
            ["--ingest-ids-json", arg_path],
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temp file %s", tmp_path)

    if code != 0:
        logger.warning("run_myhome_parser exit=%s stderr=%s", code, err[-2000:] if err else "")
        raise HTTPException(
            status_code=502,
            detail={"exit_code": code, "stderr_tail": (err or "")[-2000:], "stdout": out[:2000]},
        )
    data = _parse_json_stdout(out, script="run_myhome_parser.py")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Expected JSON object from run_myhome_parser")
    return data


@router.post("/sync-status")
def sync_status(
    settings: Annotated[Settings, Depends(get_settings)],
    max_pages: int = Query(500, ge=1, le=10_000),
) -> dict[str, Any]:
    code, out, err = _run_cli(
        settings,
        "sync_myhome_status.py",
        ["discover", "--fetch-api", "--max-pages", str(max_pages)],
    )
    data = _parse_json_stdout(out, script="sync_myhome_status.py discover")
    if code != 0:
        logger.warning("sync discover exit=%s stderr=%s", code, err[-2000:] if err else "")
        raise HTTPException(
            status_code=502,
            detail={"exit_code": code, "stderr_tail": (err or "")[-2000:]},
        )
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Expected JSON object from discover")
    return data


class MarkRejectedRequest(BaseModel):
    ids: list[int | str] = Field(min_length=1)
    reason: str = Field(default="disappeared_from_api", min_length=1, max_length=500)


@router.post("/mark-rejected")
def mark_rejected(
    body: MarkRejectedRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    ids_normalized = [str(x).strip() for x in body.ids if x is not None]
    ids_normalized = [x for x in ids_normalized if x]
    if not ids_normalized:
        raise HTTPException(status_code=400, detail="ids must contain at least one non-empty id")
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(ids_normalized, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name).resolve()
    arg_path = str(tmp_path)
    try:
        code, out, err = _run_cli(
            settings,
            "sync_myhome_status.py",
            ["mark-rejected", "--ids-json", arg_path, "--reason", body.reason],
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temp file %s", tmp_path)

    if code != 0:
        logger.warning("mark-rejected exit=%s stderr=%s", code, err[-2000:] if err else "")
        raise HTTPException(
            status_code=502,
            detail={"exit_code": code, "stderr_tail": (err or "")[-2000:]},
        )
    data = _parse_json_stdout(out, script="sync_myhome_status.py mark-rejected")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Expected JSON object from mark-rejected")
    return data
