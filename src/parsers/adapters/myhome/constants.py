"""Константы селекторов и разметки для myhome.ge (Playwright + текстовый разбор)."""

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
