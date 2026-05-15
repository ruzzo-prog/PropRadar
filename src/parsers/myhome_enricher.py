"""Обогащение лидов myhome.ge: API-детализация, телефон и PDF в адаптерном пакете.

Точка входа сохранена для совместимости; реализация в ``parsers.adapters.myhome``.
"""

from __future__ import annotations

from parsers.adapters.myhome import (
    MyHomeEnricher,
    MyHomeEnrichReport,
    MyHomePdfEnricher,
    MyHomePdfEnrichReport,
    MyHomePhoneEnricher,
    MyHomePhoneEnrichReport,
    MyHomePhoneHttpEnricher,
    MyHomePhoneHttpEnrichReport,
    extract_details_from_page_text,
    listing_url,
)
from parsers.adapters.myhome.phone import parse_phone_response as _parse_phone_response

__all__ = [
    "MyHomeEnrichReport",
    "MyHomeEnricher",
    "MyHomePdfEnrichReport",
    "MyHomePdfEnricher",
    "MyHomePhoneEnrichReport",
    "MyHomePhoneEnricher",
    "MyHomePhoneHttpEnrichReport",
    "MyHomePhoneHttpEnricher",
    "extract_details_from_page_text",
    "listing_url",
    "_parse_phone_response",
]
