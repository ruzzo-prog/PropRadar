"""Извлечение полей объявления из видимого текста страницы myhome.ge."""

from __future__ import annotations

import re
from datetime import datetime

from parsers.adapters.myhome.constants import OWNER_MARKERS
from parsers.adapters.myhome.locale import detect_listing_language
from parsers.adapters.myhome.locale import listing_url as build_listing_url
from parsers.adapters.myhome.published import parse_published_at_from_text


def listing_url(external_id: str, *, locale: str = "ru") -> str:
    """Совместимость: тот же URL, что использует enricher."""
    return build_listing_url(external_id, locale=locale)


def extract_details_from_page_text(
    text: str,
    *,
    listing_url: str | None = None,
    html_lang: str | None = None,
    published_reference: object | None = None,
) -> dict[str, object]:
    """Извлечь поля из видимого текста (юнит-тестируемая чистая функция).

    published_reference: для тестов — datetime с зоной или naive (трактуется как Tbilisi).
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    lower = normalized.lower()
    page_lang = detect_listing_language(listing_url, html_lang)

    area_m2: float | None = None
    m_area = re.search(
        r"(\d+[.,]?\d*)\s*(?:м²|м2|m²|kvm|m2\b|кв\.?\s*м|კვ\.?\s*მ)",
        lower,
        re.I,
    )
    if m_area:
        try:
            area_m2 = float(m_area.group(1).replace(",", "."))
        except ValueError:
            area_m2 = None

    rooms: int | None = None
    m_rooms = re.search(r"(\d+)\s*[-–]?\s*(?:комн|ოთახ|room)", lower, re.I)
    if m_rooms:
        rooms = int(m_rooms.group(1))

    floor: str | None = None
    m_floor = re.search(
        r"(?:этаж|სართული|floor)\s*[:\s]+(\d+\s*/\s*\d+|\d+)",
        text,
        re.I,
    )
    if m_floor:
        floor = m_floor.group(1).replace(" ", "")

    address: str | None = None
    m_addr = re.search(
        r"(?:адрес|მისამართი|address)\s*[:\s]+\s*(.+?)(?=(?:\n\s*)?(?:"
        r"район|რაიონი|district|площад|ფართ|area|фото|photo|სურათ|$))",
        text,
        re.I | re.DOTALL,
    )
    if m_addr:
        address = re.sub(r"\s+", " ", m_addr.group(1)).strip()
        if len(address) < 3:
            address = None

    district: str | None = None
    m_dist = re.search(
        r"(?:район|რაიონი|district)\s*[:\s]+\s*(.+?)(?=(?:\n\s*)?(?:"
        r"адрес|მისამართი|address|площад|ფართ|этаж|სართული|floor|$))",
        text,
        re.I | re.DOTALL,
    )
    if m_dist:
        district = re.sub(r"\s+", " ", m_dist.group(1)).strip()
        if len(district) < 2:
            district = None

    is_owner = any(m in lower for m in OWNER_MARKERS)

    description: str | None = None
    m_desc = re.search(
        r"(?:описание|აღწერა|description)\s*[:\n]?\s*([\s\S]+?)(?=(?:\n\s*)(?:"
        r"фото|photos|სურათ|characteristics|Характеристики|თვისებები|"
        r"location|მდებარეობა|similar|მსგავსი|$))",
        text,
        re.I,
    )
    if m_desc:
        raw_desc = re.sub(r"\s+", " ", m_desc.group(1)).strip()
        if len(raw_desc) >= 10:
            description = raw_desc[:8000]

    pref = published_reference
    ref_dt: datetime | None = pref if isinstance(pref, datetime) else None
    published_at = parse_published_at_from_text(text, reference=ref_dt)

    address_lang = page_lang if address else None
    district_lang = page_lang if district else None
    description_lang = page_lang if description else None

    return {
        "address": address,
        "district": district,
        "area_m2": area_m2,
        "rooms": rooms,
        "floor": floor,
        "description": description,
        "is_owner": is_owner,
        "published_at": published_at,
        "address_lang": address_lang,
        "district_lang": district_lang,
        "description_lang": description_lang,
    }


__all__ = ["extract_details_from_page_text", "listing_url"]
