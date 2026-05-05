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


def _fetch_page(
    client: httpx.Client,
    *,
    base_url: str,
    page: int,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{LIST_PATH}"
    params = dict(DEFAULT_LIST_PARAMS_BASE)
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
) -> list[dict[str, Any]]:
    """Загрузить все страницы списка (``data.data``), пока не пусто или лимит страниц."""
    out: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        batch = _fetch_page(client, base_url=base_url, page=page)
        if not batch:
            break
        out.extend(batch)
        logger.info("myhome list page=%s items=%s", page, len(batch))
    return out


def raw_items_to_external_ids(
    raw_items: list[dict[str, Any]],
    *,
    since_days: int | None = None,
) -> list[str]:
    """Извлечь ``external_id`` из элементов списка.

    При ``since_days`` оставить объекты с ``published_at`` не старше окна.
    """
    if since_days is None:
        ids: list[str] = []
        seen: set[str] = set()
        for raw in raw_items:
            lead = parse_list_item(raw)
            if lead is None:
                continue
            if lead.external_id in seen:
                continue
            seen.add(lead.external_id)
            ids.append(lead.external_id)
        return ids

    cutoff = datetime.now(UTC) - timedelta(days=since_days)
    ids_f: list[str] = []
    seen_f: set[str] = set()
    for raw in raw_items:
        lead = parse_list_item(raw)
        if lead is None:
            continue
        if lead.external_id in seen_f:
            continue
        pub = lead.published_at
        if pub is None or pub < cutoff:
            continue
        seen_f.add(lead.external_id)
        ids_f.append(lead.external_id)
    return ids_f


def fetch_all_external_ids_sync(
    client: httpx.Client,
    *,
    base_url: str,
    since_days: int | None = None,
    max_pages: int = 500,
) -> list[str]:
    """Полный список external_id: все страницы, опционально только за последние ``since_days``."""
    raw = fetch_all_list_items_sync(client, base_url=base_url, max_pages=max_pages)
    return raw_items_to_external_ids(raw, since_days=since_days)
