"""Постраничная выгрузка объявлений из GET ``/v1/statements/`` и извлечение ID."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from config.settings import Settings
from parsers.adapters.myhome.constants import LIST_PATH, REQUEST_TIMEOUT_S, api_headers
from parsers.adapters.myhome.parser import parse_list_item
from parsers.adapters.myhome.phone_http import httpx_client_kwargs_from_settings

logger = logging.getLogger(__name__)

# Параллельных страниц в одном батче (не менять без отдельного решения).
LIST_PAGE_BATCH_SIZE = 8
_DEFAULT_BATCH_SLEEP_S = 0.35

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


def list_httpx_client_kwargs(settings: Settings | None = None) -> dict[str, Any]:
    """Kwargs для ``httpx.Client`` при list fetch (proxy как в phone_http)."""
    return httpx_client_kwargs_from_settings(settings)


def _list_fetch_batch_sleep_seconds() -> float:
    raw = os.getenv("MYHOME_LIST_FETCH_BATCH_SLEEP_S", str(_DEFAULT_BATCH_SLEEP_S))
    try:
        value = float(raw)
    except ValueError:
        logger.warning("invalid MYHOME_LIST_FETCH_BATCH_SLEEP_S=%r, using default", raw)
        return _DEFAULT_BATCH_SLEEP_S
    return max(0.0, value)


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
    items, _pages = fetch_all_list_items_with_pages_sync(
        client,
        base_url=base_url,
        max_pages=max_pages,
        limit=limit,
        city=city,
        category=category,
        object_type=object_type,
        seller_type=seller_type,
    )
    return items


def _fetch_all_list_items_sequential_with_pages_sync(
    client: httpx.Client,
    *,
    base_url: str,
    max_pages: int,
    limit: int | None,
    city: str,
    category: str,
    object_type: str,
    seller_type: str,
) -> tuple[list[dict[str, Any]], int]:
    """Последовательная пагинация (ранний stop по ``limit``)."""
    out: list[dict[str, Any]] = []
    pages_fetched = 0
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
        pages_fetched += 1
        out.extend(batch)
        logger.info("myhome list page=%s items=%s", page, len(batch))
        if limit is not None and len(out) >= limit:
            break
    return out, pages_fetched


def fetch_all_list_items_with_pages_sync(
    client: httpx.Client,
    *,
    base_url: str,
    max_pages: int = 500,
    limit: int | None = None,
    city: str = "tbilisi",
    category: str = "apartment",
    object_type: str = "apartment",
    seller_type: str = "private",
) -> tuple[list[dict[str, Any]], int]:
    """Как ``fetch_all_list_items_sync``, плюс число успешно загруженных страниц.

    При ``limit`` — последовательно; иначе батчи по ``LIST_PAGE_BATCH_SIZE`` + пауза.
    """
    if limit is not None:
        return _fetch_all_list_items_sequential_with_pages_sync(
            client,
            base_url=base_url,
            max_pages=max_pages,
            limit=limit,
            city=city,
            category=category,
            object_type=object_type,
            seller_type=seller_type,
        )

    out: list[dict[str, Any]] = []
    pages_fetched = 0
    page_start = 1
    batch_sleep_s = _list_fetch_batch_sleep_seconds()
    fetch_kw = {
        "base_url": base_url,
        "city": city,
        "category": category,
        "object_type": object_type,
        "seller_type": seller_type,
    }

    while page_start <= max_pages:
        batch_end = min(page_start + LIST_PAGE_BATCH_SIZE - 1, max_pages)
        page_numbers = list(range(page_start, batch_end + 1))
        results: dict[int, list[dict[str, Any]]] = {}

        with ThreadPoolExecutor(max_workers=LIST_PAGE_BATCH_SIZE) as pool:
            futures = {
                pool.submit(_fetch_page, client, page=page_num, **fetch_kw): page_num
                for page_num in page_numbers
            }
            for future in as_completed(futures):
                page_num = futures[future]
                results[page_num] = future.result()

        stop = False
        for page_num in sorted(results):
            batch = results[page_num]
            if not batch:
                stop = True
                break
            pages_fetched += 1
            out.extend(batch)
            logger.info("myhome list page=%s items=%s", page_num, len(batch))
            if limit is not None and len(out) >= limit:
                return out, pages_fetched

        if stop:
            break

        page_start = batch_end + 1
        if page_start <= max_pages and batch_sleep_s > 0:
            time.sleep(batch_sleep_s)

    return out, pages_fetched


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


def fetch_all_external_ids_with_pages_sync(
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
) -> tuple[list[str], int]:
    """Полный список external_id и число загруженных страниц."""
    if limit is not None and limit < 1:
        msg = f"limit must be >= 1, got {limit}"
        raise ValueError(msg)

    list_limit = limit if since_days is None else None
    raw, pages_fetched = fetch_all_list_items_with_pages_sync(
        client,
        base_url=base_url,
        max_pages=max_pages,
        limit=list_limit,
        city=city,
        category=category,
        object_type=object_type,
        seller_type=seller_type,
    )
    ids = raw_items_to_external_ids(raw, limit=limit, since_days=since_days)
    return ids, pages_fetched
