"""Точечные проверки scripts/myhome_login.py (без живого браузера)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PWTimeoutError

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


def test_normalize_preserves_myhome_login_error() -> None:
    orig = _ml.MyHomeLoginError("navigate_login", "goto_timeout")
    assert _ml._normalize_login_error(orig) is orig


def test_normalize_pw_timeout_uses_default_stage() -> None:
    err = _ml._normalize_login_error(PWTimeoutError("timeout"), default_stage="manual_goto")
    assert err.stage == "manual_goto"
    assert err.reason == "timeout"


def test_normalize_playwright_error() -> None:
    err = _ml._normalize_login_error(PlaywrightError("x"), default_stage="storage_state")
    assert err.stage == "storage_state"
    assert err.reason == "playwright_error"


def test_normalize_generic_exception_class_in_reason() -> None:
    err = _ml._normalize_login_error(RuntimeError("ignored"), default_stage="auto_login")
    assert err.stage == "auto_login"
    assert err.reason == "unexpected:RuntimeError"


def test_fill_and_submit_maps_email_timeout() -> None:
    email_el = MagicMock()
    pw_el = MagicMock()
    sub_el = MagicMock()
    email_el.fill.side_effect = PWTimeoutError("t")
    with pytest.raises(_ml.MyHomeLoginError) as ei:
        _ml._fill_and_submit(email_el, pw_el, sub_el, "e", "p")
    assert ei.value.stage == "fill_submit"
    assert ei.value.reason == "email_timeout"


def test_fill_and_submit_maps_password_playwright_error() -> None:
    email_el = MagicMock()
    pw_el = MagicMock()
    sub_el = MagicMock()
    pw_el.fill.side_effect = PlaywrightError("x")
    with pytest.raises(_ml.MyHomeLoginError) as ei:
        _ml._fill_and_submit(email_el, pw_el, sub_el, "e", "p")
    assert ei.value.stage == "fill_submit"
    assert ei.value.reason == "password_failed"


def test_fill_and_submit_maps_submit_timeout() -> None:
    email_el = MagicMock()
    pw_el = MagicMock()
    sub_el = MagicMock()
    sub_el.click.side_effect = PWTimeoutError("t")
    with pytest.raises(_ml.MyHomeLoginError) as ei:
        _ml._fill_and_submit(email_el, pw_el, sub_el, "e", "p")
    assert ei.value.stage == "fill_submit"
    assert ei.value.reason == "submit_timeout"


def test_submit_selectors_exclude_has_text_pseudo() -> None:
    for sel in _ml.SUBMIT_SELECTORS:
        assert ":has-text" not in sel


def test_submit_candidates_includes_css_struct_role() -> None:
    page = MagicMock()
    inner = MagicMock()
    inner.first = MagicMock()
    mid = MagicMock()
    mid.first = MagicMock()
    inner.locator.return_value = mid
    page.locator.return_value = inner
    page.get_by_role.return_value.first = MagicMock()

    labels = [label for label, _ in _ml._submit_candidates(page)]
    assert sum(1 for x in labels if x.startswith("css:")) == len(_ml.SUBMIT_SELECTORS)
    assert "struct:form_password_submit" in labels
    assert "role:button_name_i18n" in labels
