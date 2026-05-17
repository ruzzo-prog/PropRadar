"""Unit tests for playwright launch kwargs helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from parsers.adapters.myhome.playwright_proxy import playwright_launch_kwargs_from_settings


def test_launch_kwargs_without_proxy() -> None:
    settings = MagicMock()
    settings.playwright_proxy_server = None
    kw = playwright_launch_kwargs_from_settings(settings, headless=True)
    assert kw["headless"] is True
    assert "proxy" not in kw
    assert any("AutomationControlled" in arg for arg in kw["args"])


def test_launch_kwargs_with_proxy_auth() -> None:
    settings = MagicMock()
    settings.playwright_proxy_server = "http://proxy.example:8080"
    settings.playwright_proxy_user = "user"
    settings.playwright_proxy_pass = "secret"
    kw = playwright_launch_kwargs_from_settings(settings, headless=False)
    assert kw["headless"] is False
    assert kw["proxy"] == {
        "server": "http://proxy.example:8080",
        "username": "user",
        "password": "secret",
    }
