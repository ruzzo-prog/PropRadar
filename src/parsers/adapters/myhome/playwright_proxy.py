"""Общие kwargs для ``chromium.launch`` (proxy + stealth args) из ``Settings``."""

from __future__ import annotations

from typing import Any

from config.settings import Settings

_GOOGLE_BYPASS = (
    "*.google.com,*.gstatic.com,*.googleapis.com,"
    "*.recaptcha.net,recaptcha.google.com"
)


def playwright_launch_kwargs_from_settings(
    settings: Settings,
    *,
    headless: bool,
) -> dict[str, Any]:
    launch_proxy: dict[str, str] | None = None
    if settings.playwright_proxy_server:
        launch_proxy = {"server": settings.playwright_proxy_server}
        if settings.playwright_proxy_user is not None:
            launch_proxy["username"] = settings.playwright_proxy_user
        if settings.playwright_proxy_pass is not None:
            launch_proxy["password"] = settings.playwright_proxy_pass

    launch_kw: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            f"--proxy-bypass-list={_GOOGLE_BYPASS}",
        ],
    }
    if launch_proxy is not None:
        launch_kw["proxy"] = launch_proxy
    return launch_kw
