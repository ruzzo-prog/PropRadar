"""HTTP-first извлечение телефона объявления myhome.ge из HTML (SSR / JSON без браузера).

Порядок: разбор ``__NEXT_DATA__``, затем блоки ``application/ld+json``. При отказе вернуть ``None``
(вызывающий код применяет Playwright fallback). Значение телефона в логи не выводится.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from parsers.adapters.myhome.constants import DEFAULT_USER_AGENT, REQUEST_TIMEOUT_S
from parsers.adapters.myhome.locale import listing_url

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r"<script[^>]*\bid=\"__NEXT_DATA__\"[^>]*>(?P<body>.*?)</script>",
    re.I | re.DOTALL,
)
_LD_JSON_TYPE_RE = re.compile(
    r"<script\s+[^>]*type=[\"']application/ld\+json[\"'][^>]*>(?P<body>.*?)</script>",
    re.I | re.DOTALL,
)

# Ключи, под которыми номер может лежать в JSON карточки (без попытки угадать UF_CRM)
_PHONE_KEYS = frozenset(
    {
        "phone_number",
        "phoneNumber",
        "PhoneNumber",
        "seller_phone_number",
        "mobile",
        "telephone",
        "tel",
    },
)


def _normalize_phone_digits(value: object) -> str | None:
    if isinstance(value, int):
        s = str(value)
    elif isinstance(value, str):
        s = value.strip()
    else:
        return None
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 9:
        return None
    return digits


def _phone_from_mapping(obj: dict[str, Any]) -> str | None:
    for key in _PHONE_KEYS:
        if key not in obj:
            continue
        got = _normalize_phone_digits(obj[key])
        if got:
            return got
    return None


def _walk_for_phone(obj: Any, *, depth: int = 0) -> str | None:
    if depth > 48:
        return None
    if isinstance(obj, dict):
        hit = _phone_from_mapping(obj)
        if hit:
            return hit
        for v in obj.values():
            hit = _walk_for_phone(v, depth=depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = _walk_for_phone(item, depth=depth + 1)
            if hit:
                return hit
    return None


def _extract_json_ld_phone(html: str) -> str | None:
    def walk(node: Any) -> str | None:
        return _walk_for_phone(node, depth=0)

    def process_one(blob: dict[str, Any] | list[Any]) -> str | None:
        if isinstance(blob, list):
            for item in blob:
                hit = walk(item)
                if hit:
                    return hit
            return None
        if isinstance(blob, dict):
            nodes = blob.get("@graph")
            if isinstance(nodes, list):
                top = walk(nodes)
                if top:
                    return top
            return walk(blob)
        return None

    for m in _LD_JSON_TYPE_RE.finditer(html):
        raw = m.group("body").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        hit = process_one(data if isinstance(data, (dict, list)) else {})
        if hit:
            return hit
    return None


def extract_phone_from_listing_html(html: str) -> str | None:
    """Извлечь номер из HTML без сетевого запроса (юнит-тестируемо)."""

    stripped = html.strip()
    if not stripped:
        return None

    m = _NEXT_DATA_RE.search(stripped)
    if m:
        body = m.group("body").strip()
        try:
            next_data = json.loads(body)
        except json.JSONDecodeError:
            pass
        else:
            hit = _walk_for_phone(next_data, depth=0)
            if hit:
                return hit

    hit = _extract_json_ld_phone(stripped)
    if hit:
        return hit
    return None


def _listing_page_headers(*, locale: str) -> dict[str, str]:
    raw = locale.strip("/").lower()
    lang = raw[:2] if len(raw) >= 2 else raw
    if lang not in ("ru", "ka", "en"):
        lang = "ru"
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{lang},en;q=0.8",
        "Referer": "https://www.myhome.ge/",
    }


async def get_phone(
    statement_id: str,
    client: httpx.AsyncClient,
    *,
    locale: str = "ru",
) -> str | None:
    """Скачать страницу объявления и вернуть нормализованный номер или ``None``."""

    sid = statement_id.strip()
    if not sid:
        return None
    url = listing_url(sid, locale=locale)
    headers = _listing_page_headers(locale=locale)
    try:
        response = await client.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_S,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        logger.debug("myhome http phone fetch fail ext=%s type=HTTPError", sid)
        return None
    if response.status_code != 200:
        logger.debug(
            "myhome http phone fetch ext=%s status=%s",
            sid,
            response.status_code,
        )
        return None
    phone = extract_phone_from_listing_html(response.text)
    if phone:
        logger.debug("myhome http phone ok ext=%s", sid)
    return phone
