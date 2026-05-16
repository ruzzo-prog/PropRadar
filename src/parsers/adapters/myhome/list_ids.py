"""Постраничная выгрузка объявлений из GET ``/v1/statements/`` и извлечение ID."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from parsers.adapters.myhome.constants import LIST_PATH, REQUEST_TIMEOUT_S, api_headers
from parsers.adapters.myhome.parser import parse_list_item

logger = logging.getLogger(__name__)

DEFAULT_LIST_PARAMS_BASE: dict[str, str | int] = {
    "deal_types": 1,
    "real_estate_types": 1,
    "currency_id": 1,
    "cities": 1,
    "owner_type": "physical",
    "sort": "date_desc",
}

CITY_TO_CODE: dict[str, int] = {
    "tbilisi": 1,
}

CATEGORY_TO_CODE: dict[str, int] = {
    "apartment": 1,
}

OBJECT_TYPE_TO_CODE: dict[str, int] = {
    "apartment": 1,
}

SELLER_TYPE_TO_OWNER_TYPE: dict[str, str] = {
    "private": "physical",
}


def _normalize_city(value: str) -> int:
    key = value.strip().lower()
    if key not in CITY_TO_CODE:
        msg = f"Unsupported city: {value}"
        raise ValueError(msg)
    return CITY_TO_CODE[key]


def _normalize_category(value: str) -> int:
    key = value.strip().lower()
    if key not in CATEGORY_TO_CODE:
        msg = f"Unsupported category: {value}"
        raise ValueError(msg)
    return CATEGORY_TO_CODE[key]


def _normalize_seller_type(value: str) -> str:
    key = value.strip().lower()
    if key not in SELLER_TYPE_TO_OWNER_TYPE:
        msg = f"Unsupported seller_type: {value}"
        raise ValueError(msg)
    return SELLER_TYPE_TO_OWNER_TYPE[key]


def _normalize_object_type(value: str) -> int:
    key = value.strip().lower()
    if key not in OBJECT_TYPE_TO_CODE:
        msg = f"Unsupported object_type: {value}"
        raise ValueError(msg)
    return OBJECT_TYPE_TO_CODE[key]


def _fetch_page(
    client: httpx.Client,
    *,
    base_url: str,
    page: int,
    city: str = "tbilisi",
    category: str = "apartment",
    object_type: str = "apartment",
    seller_type: str = "private",
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{LIST_PATH}"
    params = dict(DEFAULT_LIST_PARAMS_BASE)
    params["cities"] = _normalize_city(city)
    category_code = _normalize_category(category)
    object_type_code = _normalize_object_type(object_type)
    if category_code != object_type_code:
        msg = "category and object_type must map to the same real_estate_types code"
        raise ValueError(msg)
    params["real_estate_types"] = object_type_code
    params["owner_type"] = _normalize_seller_type(seller_type)
    params["page"] = page
    response = client.get(
        url,
        params=params,
        headers=api_headers(),
        timeout=REQUEST_TIMEOUT_S,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") is not True:
        msg = "myhome API returned result!=true"
        raise ValueError(msg)
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    items = data.get("data")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def fetch_all_list_items_sync(
    client: httpx.Client,
    *,
    base_url: str,
    max_pages: int = 500,
    limit: int | None = None,
    city: str = "tbilisi",
    category: str = "apartment",
    object_type: str = "apartment",
    seller_type: str = "private",
) -> list[dict[str, Any]]:
    """Загрузить страницы списка до пустой выдачи, ``max_pages`` или ``limit`` raw-элементов."""
    out: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        batch = _fetch_page(
            client,
            base_url=base_url,
            page=page,
            city=city,
            category=category,
            object_type=object_type,
            seller_type=seller_type,
        )
        if not batch:
            break
        out.extend(batch)
        logger.info("myhome list page=%s items=%s", page, len(batch))
        if limit is not None and len(out) >= limit:
            break
    return out


def _utc_now() -> datetime:
    return datetime.now(UTC)


def raw_items_to_external_ids(
    raw_items: list[dict[str, Any]],
    *,
    limit: int | None = None,
    since_days: int | None = None,
) -> list[str]:
    """Извлечь ``external_id`` из элементов списка с дедупликацией.

    При ``since_days`` оставляет только элементы с ``published_at >= now − N дней``
    (дата берётся из полей объявления, см. ``parse_list_item``). При неизвестной
    дате объявление отбрасывается.
    """
    cutoff_utc: datetime | None = None
    if since_days is not None:
        if since_days < 1:
            msg = f"since_days must be >= 1, got {since_days}"
            raise ValueError(msg)
        cutoff_utc = _utc_now() - timedelta(days=since_days)

    ids_f: list[str] = []
    seen_f: set[str] = set()
    for raw in raw_items:
        lead = parse_list_item(raw)
        if lead is None:
            continue
        if cutoff_utc is not None:
            pa = lead.published_at
            if pa is None:
                continue
            if pa < cutoff_utc:
                continue
        if lead.external_id in seen_f:
            continue
        seen_f.add(lead.external_id)
        ids_f.append(lead.external_id)
        if limit is not None and len(ids_f) >= limit:
            return ids_f
    return ids_f


def fetch_all_external_ids_sync(
    client: httpx.Client,
    *,
    base_url: str,
    since_days: int | None = None,
    max_pages: int = 500,
    limit: int | None = None,
    city: str = "tbilisi",
    category: str = "apartment",
    object_type: str = "apartment",
    seller_type: str = "private",
) -> list[str]:
    """Полный список external_id с дедупликацией; limit ограничивает число ID."""
    if limit is not None and limit < 1:
        msg = f"limit must be >= 1, got {limit}"
        raise ValueError(msg)

    list_limit = limit if since_days is None else None
    raw = fetch_all_list_items_sync(
        client,
        base_url=base_url,
        max_pages=max_pages,
        limit=list_limit,
        city=city,
        category=category,
        object_type=object_type,
        seller_type=seller_type,
    )
    return raw_items_to_external_ids(raw, limit=limit, since_days=since_days)
