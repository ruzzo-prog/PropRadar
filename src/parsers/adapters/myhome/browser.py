"""Общие операции Playwright для адаптера myhome (попапы, скриншоты, чтение текста)."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Page

from domain.lead import Lead
from parsers.adapters.myhome.constants import (
    POPUP_CLOSE_SELECTORS,
    TW_MS,
)

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
