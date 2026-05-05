"""Определение языка страницы объявления (URL → html lang)."""

from __future__ import annotations

import re
from typing import Final

_VALID: Final[frozenset[str]] = frozenset({"ka", "ru", "en"})


def listing_url(external_id: str, *, locale: str = "ru") -> str:
    loc = locale.strip("/") or "ru"
    return f"https://www.myhome.ge/{loc}/pr/{external_id}/"


def detect_listing_language(listing_url_str: str | None, html_lang: str | None) -> str | None:
    if listing_url_str:
        m = re.search(r"myhome\.ge/([a-z]{2})/pr/", listing_url_str, re.I)
        if m:
            cand = m.group(1).lower()
            if cand in _VALID:
                return cand
    if html_lang:
        base = html_lang.strip().split("-", 1)[0].lower()
        if base in _VALID:
            return base
    return None
