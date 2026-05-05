"""HTTP-константы myhome.ge API (без браузера): базовые URL, заголовки, таймаут."""

from __future__ import annotations

DEFAULT_MYHOME_API_BASE = "https://api-statements.tnet.ge"
LIST_PATH = "/v1/statements/"
DETAIL_PATH_TMPL = "/v1/statements/{statement_id}"

DEFAULT_ORIGIN = "https://www.myhome.ge"
DEFAULT_REFERER = "https://www.myhome.ge/"

REQUEST_TIMEOUT_S = 60.0

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def api_headers(*, website_key: str = "myhome") -> dict[str, str]:
    """Заголовки для api-statements.tnet.ge (публичный сайт-ключ в заголовке)."""
    return {
        "X-Website-Key": website_key,
        "Accept": "application/json",
        "Origin": DEFAULT_ORIGIN,
        "Referer": DEFAULT_REFERER,
        "User-Agent": DEFAULT_USER_AGENT,
    }


PHONE_URL_PART = "statements/phone/show"
OWNER_MARKERS = ("я собственник", "ვარ მესაკუთრე", "i am the owner", "i'm the owner")
TW_MS = 30_000

POPUP_CLOSE_SELECTORS = [
    "button[aria-label='close']",
    "button[aria-label='Close']",
    "[class*='modal'] [class*='close']",
    "[class*='popup'] [class*='close']",
    "[class*='dialog'] button",
    "button[class*='dismiss']",
]

BTN_SELECTORS = [
    "button:has(span:text('ნომრის ნახვა'))",
    "button:has-text('ნომრის')",
    "a:has-text('ნომრის')",
]
