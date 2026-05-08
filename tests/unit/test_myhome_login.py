"""Точечные проверки URL-логики scripts/myhome_login.py (без Playwright)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "myhome_login_script",
    _REPO / "scripts" / "myhome_login.py",
)
assert _spec and _spec.loader
_ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ml)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.myhome.ge/ru/", True),
        ("https://www.myhome.ge/ru/listing/1", True),
        ("https://auth.tnet.ge/ru/user/login/?Continue=https://www.myhome.ge/", False),
        ("https://www.myhome.ge/ru/user/login/", False),
        ("https://www.myhome.ge/en/login", False),
        ("https://www.myhome.ge/ru/signin", False),
        ("https://example.com/", False),
    ],
)
def test_url_indicates_logged_in(url: str, expected: bool) -> None:
    assert _ml._url_indicates_logged_in(url) is expected
