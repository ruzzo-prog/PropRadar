"""Headful Playwright: вход на myhome.ge.

Сохраняет storage_state в путь из ``MYHOME_SESSION_PATH`` (или настройки).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Locator, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError
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


def _normalize_login_error(
    exc: BaseException,
    *,
    default_stage: str = "unexpected",
) -> MyHomeLoginError:
    """Приводит исключения Playwright и прочие сбои к ``MyHomeLoginError``.

    Текст исходного исключения в ``reason`` не попадает (без утечек в лог).
    """
    if isinstance(exc, MyHomeLoginError):
        return exc
    if isinstance(exc, PWTimeoutError):
        return MyHomeLoginError(default_stage, "timeout")
    if isinstance(exc, PlaywrightError):
        return MyHomeLoginError(default_stage, "playwright_error")
    return MyHomeLoginError(default_stage, f"unexpected:{type(exc).__name__}")


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
    try:
        email_el.fill(email, timeout=15_000)
    except PWTimeoutError as exc:
        raise MyHomeLoginError("fill_submit", "email_timeout") from exc
    except PlaywrightError as exc:
        raise MyHomeLoginError("fill_submit", "email_failed") from exc
    try:
        password_el.fill(password, timeout=15_000)
    except PWTimeoutError as exc:
        raise MyHomeLoginError("fill_submit", "password_timeout") from exc
    except PlaywrightError as exc:
        raise MyHomeLoginError("fill_submit", "password_failed") from exc
    try:
        submit_el.click(timeout=15_000)
    except PWTimeoutError as exc:
        raise MyHomeLoginError("fill_submit", "submit_timeout") from exc
    except PlaywrightError as exc:
        raise MyHomeLoginError("fill_submit", "submit_failed") from exc


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
    try:
        page.goto(
            _resolve_login_url(),
            wait_until="domcontentloaded",
            timeout=120_000,
        )
    except PWTimeoutError as exc:
        raise MyHomeLoginError("navigate_login", "goto_timeout") from exc
    except PlaywrightError as exc:
        raise MyHomeLoginError("navigate_login", "goto_failed") from exc
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
    try:
        with sync_playwright() as pw:
            browser = None
            context: BrowserContext | None = None
            page: Page | None = None
            try:
                try:
                    browser = pw.chromium.launch(headless=True)
                except PWTimeoutError as exc:
                    raise MyHomeLoginError("launch_browser", "timeout") from exc
                except PlaywrightError as exc:
                    raise MyHomeLoginError("launch_browser", "launch_failed") from exc
                try:
                    context = browser.new_context(locale="ru-RU")
                except PlaywrightError as exc:
                    raise MyHomeLoginError("browser_context", "new_context_failed") from exc
                if debug:
                    try:
                        context.tracing.start(screenshots=True, snapshots=True)
                    except Exception:
                        logger.warning(
                            "myhome_login tracing start failed (stage=tracing_start)",
                            exc_info=True,
                        )
                try:
                    page = context.new_page()
                except PlaywrightError as exc:
                    raise MyHomeLoginError("browser_page", "new_page_failed") from exc
                try:
                    if creds_ok:
                        try:
                            _run_auto_login(
                                page,
                                settings.myhome_email or "",
                                settings.myhome_password or "",
                            )
                        except Exception as exc:
                            err = _normalize_login_error(exc, default_stage="auto_login")
                            logger.error(
                                "Автовход не удался: stage=%s reason=%s",
                                err.stage,
                                err.reason,
                            )
                            if debug and page is not None:
                                _debug_failure_shot(page, state_path)
                            exit_code = 1
                    else:
                        try:
                            page.goto(
                                "https://www.myhome.ge/ru/",
                                wait_until="domcontentloaded",
                                timeout=120_000,
                            )
                        except Exception as exc:
                            err = _normalize_login_error(exc, default_stage="manual_goto")
                            logger.error(
                                "Ручной вход: stage=%s reason=%s",
                                err.stage,
                                err.reason,
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
                                err = MyHomeLoginError("manual_stdin", "eof")
                                logger.error(
                                    "Ручной вход: stage=%s reason=%s",
                                    err.stage,
                                    err.reason,
                                )
                                exit_code = 1
                finally:
                    if debug and context is not None:
                        try:
                            context.tracing.stop(
                                path=str(state_path.parent / "myhome_login_trace.zip"),
                            )
                        except Exception:
                            trace_stop_failed = True
                            logger.warning(
                                "myhome_login trace stop failed (stage=trace_stop)",
                                exc_info=True,
                            )

                if exit_code == 0:
                    if debug and trace_stop_failed:
                        logger.error(
                            "Сессия не сохранена: stage=trace_stop reason=stop_failed",
                        )
                        exit_code = 1
                    elif context is not None:
                        try:
                            context.storage_state(path=str(state_path))
                        except Exception as exc:
                            err = _normalize_login_error(exc, default_stage="storage_state")
                            logger.error(
                                "Не удалось сохранить сессию: stage=%s reason=%s",
                                err.stage,
                                err.reason,
                            )
                            exit_code = 1
            finally:
                if browser is not None:
                    browser.close()
    except MyHomeLoginError as exc:
        logger.error("myhome_login: stage=%s reason=%s", exc.stage, exc.reason)
        return 1

    if exit_code != 0:
        return exit_code
    logger.info("Готово.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MyHomeLoginError as exc:
        logging.getLogger("myhome_login").error(
            "myhome_login: stage=%s reason=%s",
            exc.stage,
            exc.reason,
        )
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        err = _normalize_login_error(exc)
        logging.getLogger("myhome_login").error(
            "myhome_login: stage=%s reason=%s",
            err.stage,
            err.reason,
        )
        raise SystemExit(1) from exc
