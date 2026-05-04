"""Headful Playwright: вход на myhome.ge.

Сохраняет storage_state в scripts/myhome_session.json.
"""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from config.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("myhome_login")

_STATE_FILE = Path(__file__).resolve().parent / "myhome_session.json"


def _try_auto_login(page: Page, email: str, password: str) -> None:
    """Лучший-effort: не логировать пароль; селекторы сайта могут меняться."""
    for sel in (
        'a[href*="login"]',
        'a[href*="sign"]',
        'a[href*="auth"]',
    ):
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            loc.click(timeout=15_000)
            break
    page.wait_for_load_state("domcontentloaded", timeout=30_000)
    for email_sel in ('input[type="email"]', 'input[name="email"]', "#email"):
        el = page.locator(email_sel).first
        if el.count():
            el.fill(email, timeout=10_000)
            break
    for pass_sel in ('input[type="password"]', 'input[name="password"]', "#password"):
        el = page.locator(pass_sel).first
        if el.count():
            el.fill(password, timeout=10_000)
            break
    for btn in ('button[type="submit"]', 'button:has-text("Войти")', 'button:has-text("შესვლა")'):
        loc = page.locator(btn).first
        if loc.count() and loc.is_visible():
            loc.click(timeout=15_000)
            break


def main() -> int:
    settings = Settings()
    logger.info("Откроется окно браузера. Сессия будет записана в %s", _STATE_FILE)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        page.goto("https://www.myhome.ge/ru/", wait_until="domcontentloaded", timeout=120_000)

        if settings.myhome_email and settings.myhome_password:
            try:
                _try_auto_login(page, settings.myhome_email, settings.myhome_password)
            except Exception:
                logger.warning("Автовход не удался — выполните вход вручную в окне браузера.")

        print("После успешного входа нажмите Enter в этой консоли, чтобы сохранить сессию.")
        try:
            input()
        except EOFError:
            logger.error("Нет интерактивного stdin — прервите и запустите вручную.")
            return 1

        context.storage_state(path=str(_STATE_FILE))
        browser.close()

    logger.info("Готово.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("myhome_login").error("%s: %s", type(exc).__name__, exc)
        raise SystemExit(1) from exc
