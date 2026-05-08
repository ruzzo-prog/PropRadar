"""Headful Playwright: вход на myhome.ge.

Сохраняет storage_state в путь из ``MYHOME_SESSION_PATH`` (или настройки).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeoutError

from config.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("myhome_login")

# Канон входа TNET (редирект на myhome.ge после успеха). Переопределение: MYHOME_LOGIN_URL.
DEFAULT_MYHOME_LOGIN_URL = (
    "https://auth.tnet.ge/ru/user/login/?Continue=https://www.myhome.ge/ru/"
)

EMAIL_SELECTORS = (
    'input[type="email"]',
    'input[name="email"]',
    "#email",
    'input[autocomplete="username"]',
)
PASSWORD_SELECTORS = (
    'input[type="password"]',
    'input[name="password"]',
    "#password",
    'input[autocomplete="current-password"]',
)
SUBMIT_SELECTORS = (
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Войти")',
    'button:has-text("შესვლა")',
    'button:has-text("Login")',
)


class MyHomeLoginError(RuntimeError):
    """Ошибка автологина; ``stage`` и ``reason`` без PII (без email/url с токенами)."""

    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"{stage}:{reason}")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _resolve_login_url() -> str:
    raw = os.environ.get("MYHOME_LOGIN_URL", "").strip()
    if raw:
        return raw
    return DEFAULT_MYHOME_LOGIN_URL


def _first_visible_field(page: Page, selectors: tuple[str, ...], role: str) -> Locator:
    last_err: PWTimeoutError | None = None
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() == 0:
            continue
        try:
            loc.wait_for(state="visible", timeout=15_000)
            return loc
        except PWTimeoutError as exc:
            last_err = exc
            continue
    if last_err is not None:
        raise MyHomeLoginError("locate_fields", f"missing_visible:{role}") from last_err
    raise MyHomeLoginError("locate_fields", f"missing_field:{role}")


def _locate_required_controls(page: Page) -> tuple[Locator, Locator, Locator]:
    em = _first_visible_field(page, EMAIL_SELECTORS, "email")
    pw_field = _first_visible_field(page, PASSWORD_SELECTORS, "password")
    sub = _first_visible_field(page, SUBMIT_SELECTORS, "submit")
    return em, pw_field, sub


def _url_indicates_logged_in(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "auth.tnet.ge" in host and "/user/login" in path:
        return False
    if "myhome.ge" not in host:
        return False
    for marker in (
        "/user/login",
        "/login",
        "/signin",
        "/sign-in",
        "/oauth",
        "/auth/",
    ):
        if marker in path:
            return False
    return True


def _fill_and_submit(
    email_el: Locator,
    password_el: Locator,
    submit_el: Locator,
    email: str,
    password: str,
) -> None:
    email_el.fill(email, timeout=15_000)
    password_el.fill(password, timeout=15_000)
    submit_el.click(timeout=15_000)


def _wait_auth_success(page: Page) -> None:
    """Не полагаемся на networkidle: ждём устойчивый признак (URL на myhome.ge)."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=45_000)
    except PWTimeoutError as exc:
        raise MyHomeLoginError("verify_auth", "load_state_timeout") from exc
    try:
        page.wait_for_url(_url_indicates_logged_in, timeout=90_000)
    except PWTimeoutError as exc:
        raise MyHomeLoginError("verify_auth", "redirect_timeout") from exc
    if not _url_indicates_logged_in(page.url):
        raise MyHomeLoginError("verify_auth", "url_not_authenticated")


def _run_auto_login(page: Page, email: str, password: str) -> None:
    page.goto(
        _resolve_login_url(),
        wait_until="domcontentloaded",
        timeout=120_000,
    )
    em, pw_field, sub = _locate_required_controls(page)
    _fill_and_submit(em, pw_field, sub, email, password)
    _wait_auth_success(page)


def _debug_failure_shot(page: Page, state_path: Path) -> None:
    try:
        page.screenshot(path=str(state_path.parent / "myhome_login_fail.png"), full_page=True)
    except Exception:
        logger.warning("myhome_login debug screenshot failed", exc_info=True)


def main() -> int:
    settings = Settings()
    state_path = settings.myhome_session_path
    if not state_path.is_absolute():
        state_path = (Path.cwd() / state_path).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    creds_ok = bool(settings.myhome_email and settings.myhome_password)
    if not creds_ok and not sys.stdin.isatty():
        logger.error(
            "Задайте MYHOME_EMAIL и MYHOME_PASSWORD или запускайте в интерактивной консоли.",
        )
        return 1

    debug = _env_truthy("MYHOME_LOGIN_DEBUG")
    logger.info("Откроется окно браузера. Сессия будет записана в %s", state_path)

    exit_code = 0
    trace_stop_failed = False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(locale="ru-RU")
        if debug:
            context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()
        try:
            if creds_ok:
                try:
                    _run_auto_login(
                        page,
                        settings.myhome_email or "",
                        settings.myhome_password or "",
                    )
                except MyHomeLoginError as exc:
                    logger.error(
                        "Автовход не удался: stage=%s type=%s",
                        exc.stage,
                        exc.reason,
                    )
                    if debug:
                        _debug_failure_shot(page, state_path)
                    exit_code = 1
                except Exception:
                    logger.exception("Автовход не удался: stage=unexpected type=error")
                    if debug:
                        _debug_failure_shot(page, state_path)
                    exit_code = 1
            else:
                try:
                    page.goto(
                        "https://www.myhome.ge/ru/",
                        wait_until="domcontentloaded",
                        timeout=120_000,
                    )
                except Exception:
                    logger.exception(
                        "Ручной вход: не удалось открыть стартовую страницу (stage=manual_goto)",
                    )
                    exit_code = 1
                if exit_code == 0:
                    print("Выполните вход вручную в окне браузера.")
                    print(
                        "После успешного входа нажмите Enter в этой консоли, "
                        "чтобы сохранить сессию.",
                    )
                    try:
                        input()
                    except EOFError:
                        logger.error("Нет интерактивного stdin.")
                        exit_code = 1
        finally:
            if debug:
                try:
                    context.tracing.stop(path=str(state_path.parent / "myhome_login_trace.zip"))
                except Exception:
                    trace_stop_failed = True
                    logger.warning("myhome_login trace stop failed", exc_info=True)

        if exit_code == 0:
            if debug and trace_stop_failed:
                logger.error(
                    "Сессия не сохранена: остановка trace завершилась с ошибкой (stage=trace_stop)",
                )
                exit_code = 1
            else:
                context.storage_state(path=str(state_path))
        browser.close()

    if exit_code != 0:
        return exit_code
    logger.info("Готово.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("myhome_login").error("%s: %s", type(exc).__name__, exc)
        raise SystemExit(1) from exc
