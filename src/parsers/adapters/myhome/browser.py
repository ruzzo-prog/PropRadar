"""Операции Playwright для myhome enricher (без изменения таймингов ожидания)."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeoutError

from domain.lead import Lead
from parsers.adapters.myhome.constants import (
    BTN_SELECTORS,
    POPUP_CLOSE_SELECTORS,
    TW_MS,
)
from parsers.adapters.myhome.phone import parse_phone_response

logger = logging.getLogger(__name__)


def screenshot_dir() -> Path:
    root = Path(__file__).resolve().parent.parent.parent.parent.parent
    return root / "scripts" / "debug_screenshots"


def dismiss_popup(page: Page) -> None:
    """Escape + поиск крестика модала. Не бросает исключений."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    except Exception:
        pass
    for sel in POPUP_CLOSE_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click(timeout=1500)
                page.wait_for_timeout(400)
                logger.debug("popup dismissed sel=%r", sel)
                return
        except Exception:
            continue


def save_timeout_shot(page: Page, lead: Lead) -> None:
    name = str(lead.id) if lead.id else lead.external_id
    out_dir = screenshot_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True, timeout=TW_MS)
    except Exception:
        logger.warning("debug_screenshot_failed ext=%s", lead.external_id)


def visible_text(page: Page) -> str:
    try:
        return page.locator("main").first.inner_text(timeout=TW_MS)
    except Exception:
        return page.locator("body").inner_text(timeout=TW_MS)


def click_show_phone(page: Page, external_id: str) -> str:
    tw = 15_000
    out_dir = screenshot_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(
            path=str(out_dir / f"before_click_{external_id}.png"),
            full_page=True,
            timeout=TW_MS,
        )
    except Exception:
        logger.warning("before_click screenshot failed ext=%s", external_id)

    btn = None
    for sel in BTN_SELECTORS:
        loc = page.locator(sel).first
        if loc.count() > 0:
            btn = loc
            logger.debug("phone_btn in_dom sel=%r ext=%s", sel, external_id)
            break
    if btn is None:
        raise PWTimeoutError(f"phone button not in DOM ext={external_id}")

    with page.expect_response(
        lambda r: "phone/show" in r.url and r.status == 200,
        timeout=tw,
    ) as resp_info:
        handle = btn.element_handle(timeout=tw)
        if handle is None:
            raise PWTimeoutError(f"phone button no element_handle ext={external_id}")
        page.evaluate("el => el.click()", handle)
    return parse_phone_response(resp_info.value)
