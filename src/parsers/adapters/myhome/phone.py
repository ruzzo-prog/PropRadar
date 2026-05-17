"""Телефон объявления myhome.ge: Playwright-клик по UI и разбор ответа ``phone/show``.

На карточке подмешивается reCAPTCHA v3; токен и номер телефона в логи не пишутся.
Отдельный вход на сайт не обязателен для типичных объявлений физлиц — состояние браузера
опционально задаётся файлом ``MYHOME_PLAYWRIGHT_STORAGE`` (если задан и существует).
"""

from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import os
import random
import subprocess
import time
from playwright.sync_api import Browser, Page, Response, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright_stealth import Stealth

from config.settings import Settings
from domain.lead import Lead
from parsers.adapters.myhome.browser import dismiss_popup, save_timeout_shot
from parsers.adapters.myhome.constants import BTN_SELECTORS, TW_MS
from parsers.adapters.myhome.extract import listing_url
from parsers.adapters.myhome.playwright_proxy import playwright_launch_kwargs_from_settings
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"\+?[0-9]{9,13}")
_DOM_204_PHONE_RE = re.compile(r"\+?995[\s\d]{9,14}")

_MYHOME_PHONE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

# JS: unhide any display:none ancestor, then click. Works even when the
# phone button lives inside a hidden container (e.g. a lazy-rendered sidebar).
_JS_CLICK_PHONE_BTN = """() => {
    const selectors = """ + json.dumps(BTN_SELECTORS) + """;
    for (const sel of selectors) {
        const btns = [...document.querySelectorAll(sel)];
        if (!btns.length) continue;
        const btn = btns[0];
        // Unhide display:none ancestors so grecaptcha fires correctly
        let el = btn;
        while (el && el !== document.body) {
            if (window.getComputedStyle(el).display === 'none') {
                el.style.display = 'block';
            }
            el = el.parentElement;
        }
        btn.click();
        return 'clicked:' + btn.textContent.trim().slice(0, 40);
    }
    return 'not_found';
}"""


def parse_phone_response(response: Response) -> str:
    """Разобрать JSON ответа телефона."""
    if response.status == 401:
        raise RuntimeError("phone_api_unauthorized")
    if response.status >= 400:
        raise RuntimeError(f"phone_api_http_{response.status}")
    payload = response.json()
    if payload.get("result") is not True:
        raise RuntimeError("phone_api_denied")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("phone_api_shape")
    raw = data.get("phone_number")
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("phone_api_empty")
    return raw.strip()


def _extract_phone_from_dom(page: Page) -> str | None:
    """Найти номер телефона в DOM после клика."""
    try:
        # Search all spans for +995 phone pattern
        spans = page.query_selector_all("span")
        for span in spans:
            text = span.inner_text(timeout=500)
            if _PHONE_RE.search(text):
                return _PHONE_RE.search(text).group(0)
    except Exception:
        pass
    try:
        # Also check button text (phone might replace button label)
        for sel in BTN_SELECTORS:
            loc = page.locator(sel).first
            if loc.count() > 0:
                text = loc.inner_text(timeout=500)
                if _PHONE_RE.search(text):
                    return _PHONE_RE.search(text).group(0)
    except Exception:
        pass
    return None


def _phone_from_body_text(page: Page) -> str:
    """Извлечь +995… из DOM после phone/show 204 (тело ответа пустое)."""
    text = page.locator("body").inner_text(timeout=TW_MS)
    m = _DOM_204_PHONE_RE.search(text)
    if not m:
        raise RuntimeError("phone_btn_digits_missing")
    normalized = re.sub(r"\s+", "", m.group(0))
    if not normalized.startswith("+"):
        normalized = "+" + normalized
    return normalized


def click_show_phone(page: Page, external_id: str) -> str:
    """Ждать появления кнопки (React hydration ~5-9s), кликнуть, ждать телефон в DOM."""
    # Wait for phone button (React hydration takes ~5-9s after domcontentloaded)
    btn_loc = page.locator("text=ნომრის ნახვა").first
    try:
        btn_loc.wait_for(state="attached", timeout=TW_MS)
    except Exception as exc:
        logger.debug("btn_wait_fail ext=%s: %s", external_id, exc)
        raise RuntimeError("phone_btn_not_found")

    # phone/show: 200 — JSON с номером; 204 — No Content, номер в DOM после React update
    with page.expect_response(
        lambda r: "phone/show" in r.url and r.status in (200, 204),
        timeout=TW_MS,
    ) as resp_info:
        btn_loc.evaluate("""el => {
            let e = el;
            while (e && e !== document.body) {
                if (window.getComputedStyle(e).display === 'none') e.style.display = 'block';
                if (window.getComputedStyle(e).visibility === 'hidden') e.style.visibility = 'visible';
                e = e.parentElement;
            }
            el.click();
        }""")

    resp = resp_info.value
    if resp.status == 204:
        phone = _phone_from_body_text(page)
        logger.debug("phone_from_dom ext=%s", external_id)
        return phone
    phone = parse_phone_response(resp)
    logger.debug("phone_from_api ext=%s", external_id)
    return phone

@dataclass
class MyHomePhoneEnrichReport:
    enriched: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class MyHomePhoneEnricher:
    """Очередь телефона: только поле ``phone`` через Playwright."""

    def __init__(
        self,
        repository: LeadRepository,
        *,
        locale: str = "ru",
        headless: bool = True,
        storage_state_path: Path | None = None,
    ) -> None:
        self._repository = repository
        self._locale = locale
        self._headless = headless
        self._storage_state_path = storage_state_path


    def _load_storage(self) -> dict | None:
        """Read session from disk; re-login if AccessToken is expired."""
        if self._storage_state_path is None or not self._storage_state_path.exists():
            return None
        storage = json.loads(self._storage_state_path.read_text(encoding="utf-8"))
        # Check if token is expired — if so, re-login before proceeding
        try:
            import base64 as _b64, time as _time
            token_val = next(
                (c["value"] for c in storage.get("cookies", []) if c["name"] == "AccessToken"),
                None,
            )
            if token_val:
                payload = json.loads(_b64.b64decode(token_val.split(".")[1] + "=="))
                remaining = payload.get("expires_at", 0) - _time.time()
                if remaining < 60:
                    logger.info("access_token_expired remaining=%.0fs — re-logging in", remaining)
                    login_script = Path(__file__).parent.parent.parent.parent / "scripts" / "myhome_login.py"
                    if login_script.exists():
                        subprocess.run(
                            ["python3", str(login_script)],
                            timeout=120,
                            capture_output=True,
                        )
                        storage = json.loads(self._storage_state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("token_check_failed: %s", exc)
        tnet_token = next(
            (c for c in storage.get("cookies", []) if c["name"] == "AccessToken"),
            None,
        )
        if tnet_token:
            mh_cookie = copy.deepcopy(tnet_token)
            mh_cookie["domain"] = "www.myhome.ge"
            mh_cookie["path"] = "/"
            mh_cookie["sameSite"] = "None"
            storage["cookies"].append(mh_cookie)
        return storage

    def enrich_leads(self, leads: Iterable[Lead]) -> MyHomePhoneEnrichReport:
        report = MyHomePhoneEnrichReport()
        items = list(leads)
        if not items:
            return report

        app_settings = Settings()
        launch_kw = playwright_launch_kwargs_from_settings(
            app_settings,
            headless=self._headless,
        )

        for lead in items:
            # Re-read session from disk each lead so refreshed tokens are picked up
            lead_storage = self._load_storage()
            # Kill leftover Chrome processes before each lead
            subprocess.run(["pkill", "-9", "-f", "chromium"], capture_output=True)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(**launch_kw)
                try:
                    err = self._enrich_one_isolated(browser, lead, lead_storage)
                finally:
                    browser.close()
            # Kill any remaining Chrome after close
            subprocess.run(["pkill", "-9", "-f", "chromium"], capture_output=True)
            # Reap zombie child processes so process table doesn't fill up
            try:
                while True:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
            except ChildProcessError:
                pass
            # Пауза между лидами — снижает риск CF rate-limiting
            time.sleep(random.uniform(2.0, 4.0))
            if err is None:
                report.enriched += 1
            else:
                report.failed += 1
                report.errors.append(err)
        return report

    def _enrich_one_isolated(self, browser: Browser, lead: Lead, storage) -> str | None:
        lid = str(lead.id) if lead.id else "none"
        label = f"source=myhome id={lid} ext={lead.external_id}"
        context = browser.new_context(
            locale=self._locale,
            storage_state=storage,
            user_agent=_MYHOME_PHONE_USER_AGENT,
        )
        try:
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            try:
                if lead.id is None:
                    return f"no_lead_id:{lead.external_id}"

                url = listing_url(lead.external_id, locale=self._locale)
                page.goto(url, wait_until="domcontentloaded", timeout=TW_MS)
                # CF challenge executes JS after domcontentloaded — wait for it to resolve
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                if "Just a moment" in page.title() or "cf-challenge" in page.content():
                    logger.warning("cloudflare_block ext=%s", lead.external_id)
                    save_timeout_shot(page, lead)
                    return "CloudflareBlock"

                dismiss_popup(page)

                phone = click_show_phone(page, lead.external_id)
                merged = lead.model_copy(update={"phone": phone})
                self._repository.update_enriched_fields(merged)
                logger.info("phone_enriched ext=%s", lead.external_id)
            except PWTimeoutError:
                save_timeout_shot(page, lead)
                logger.warning("myhome phone enrich fail %s type=TimeoutError", label)
                return f"{lead.external_id}:TimeoutError"
            except Exception as exc:
                logger.warning("myhome phone enrich fail %s type=%s", label, type(exc).__name__)
                if type(exc).__name__ == "TimeoutError":
                    save_timeout_shot(page, lead)
                return f"{lead.external_id}:{type(exc).__name__}"
            return None
        finally:
            try:
                updated = context.storage_state()
                if self._storage_state_path is not None:
                    import json as _json
                    self._storage_state_path.write_text(
                        _json.dumps(updated, ensure_ascii=False), encoding='utf-8'
                    )
            except Exception:
                pass
            context.close()
