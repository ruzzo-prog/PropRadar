from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_discover_without_api_source_exits_2_with_json() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "sync_myhome_status.py"
    env = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    proc = subprocess.run(
        [sys.executable, str(script), "discover"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 2
    assert proc.stdout
    body = json.loads(proc.stdout.strip())
    assert body.get("error") == "missing_api_ids_source"
    assert "api-ids-json" in (body.get("message") or "")
