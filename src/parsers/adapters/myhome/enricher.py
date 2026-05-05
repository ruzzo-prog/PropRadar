"""Обогащение карточки myhome.ge через GET ``/v1/statements/{id}`` (без Playwright).

Очередь detail: ``status=new``, ``source=myhome``, и
``address IS NULL OR price_gel IS NULL`` (см. ``list_pending_detail_enrichment``).

Телефон и PDF выносятся в отдельные очереди: ``phone.py``, ``pdf.py``.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from domain.lead import Lead
from parsers.adapters.myhome.constants import DETAIL_PATH_TMPL, REQUEST_TIMEOUT_S, api_headers
from parsers.adapters.myhome.published import TBILISI
from parsers.adapters.myhome.schema import MyHomeStatementPayload
from repositories.base import LeadRepository

logger = logging.getLogger(__name__)

_BR_TAG_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_TAGS_RE = re.compile(r"<[^>]+>")


def strip_html_comment_to_plain_text(raw: str) -> str:
    """Удалить HTML из поля комментария API (идемпотентно для уже чистого текста)."""
    text = raw.strip()
    if not text:
        return ""
    text = html.unescape(text)
    text = _BR_TAG_RE.sub("\n", text)
    text = _TAGS_RE.sub("", text)
    text = html.unescape(text.strip())
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


@dataclass
class MyHomeEnrichReport:
    enriched: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def parse_api_local_timestamp(value: str | None) -> datetime | None:
    """Разобрать ``YYYY-MM-DD HH:MM:SS`` как локальное время Asia/Tbilisi → UTC."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            naive = datetime.strptime(text, fmt)
            return naive.replace(tzinfo=TBILISI).astimezone(UTC)
        except ValueError:
            continue
    return None


def _price_slot(statement: dict[str, Any], currency_key: str) -> dict[str, Any]:
    block = statement.get("price")
    if not isinstance(block, dict):
        return {}
    slot = block.get(currency_key)
    if slot is None and currency_key.isdigit():
        slot = block.get(int(currency_key))
    return slot if isinstance(slot, dict) else {}


def statement_to_lead_updates(statement: dict[str, Any]) -> dict[str, Any]:
    """Собрать непустые поля для ``Lead.model_copy(update=...)`` из ``statement``."""
    payload = MyHomeStatementPayload.model_validate(statement)
    updates: dict[str, Any] = {}
    lang = "ka"

    slot_gel = _price_slot(statement, "1")
    gel_total = slot_gel.get("price_total")
    if gel_total is not None:
        updates["price_gel"] = int(gel_total)

    slot_usd = _price_slot(statement, "2")
    usd_total = slot_usd.get("price_total")
    per_m2 = slot_usd.get("price_square")
    if usd_total is not None:
        updates["price_usd"] = int(usd_total)
    if per_m2 is not None:
        updates["price_m2_usd"] = int(per_m2)

    uid = payload.uuid
    if isinstance(uid, str) and uid:
        try:
            updates["source_listing_uuid"] = UUID(uid)
        except ValueError:
            pass

    if isinstance(statement.get("address"), str) and statement["address"].strip():
        updates["address"] = statement["address"].strip()
        updates["address_lang"] = lang
    if isinstance(statement.get("district_name"), str) and statement["district_name"].strip():
        updates["district"] = statement["district_name"].strip()
        updates["district_lang"] = lang
    if isinstance(statement.get("comment"), str) and statement["comment"].strip():
        updates["description"] = strip_html_comment_to_plain_text(statement["comment"])
        updates["description_lang"] = lang

    area = statement.get("area")
    if isinstance(area, (int, float)):
        updates["area_m2"] = Decimal(str(area))

    fl = statement.get("floor")
    tf = statement.get("total_floors")
    floor_s: str | None = None
    if isinstance(fl, int) and isinstance(tf, int):
        floor_s = f"{fl}/{tf}"
    elif isinstance(fl, int):
        floor_s = str(fl)
    elif isinstance(fl, str) and fl.strip():
        floor_s = fl.strip()
    if floor_s:
        updates["floor"] = floor_s

    room = statement.get("room")
    if isinstance(room, int):
        updates["rooms"] = room
    elif isinstance(room, str) and room.strip().isdigit():
        updates["rooms"] = int(room.strip())

    if statement.get("is_owner") is True:
        updates["is_owner"] = True

    lat = statement.get("lat")
    lng = statement.get("lng")
    if isinstance(lat, (int, float)):
        updates["geo_lat"] = Decimal(str(lat))
    if isinstance(lng, (int, float)):
        updates["geo_lng"] = Decimal(str(lng))

    views = statement.get("views")
    if isinstance(views, int):
        updates["listing_views"] = views

    pub = parse_api_local_timestamp(statement.get("created_at")) or parse_api_local_timestamp(
        statement.get("last_updated"),
    )
    if pub is not None:
        updates["published_at"] = pub

    updates["myhome_statement_json"] = dict(statement)
    return updates


def fetch_statement_detail(
    client: httpx.Client,
    *,
    base_url: str,
    external_id: str,
) -> dict[str, Any]:
    path = DETAIL_PATH_TMPL.format(statement_id=external_id)
    url = f"{base_url.rstrip('/')}{path}"
    response = client.get(url, headers=api_headers(), timeout=REQUEST_TIMEOUT_S)
    response.raise_for_status()
    body = response.json()
    if body.get("result") is not True:
        raise ValueError("myhome_detail_result_not_true")
    data = body.get("data")
    if not isinstance(data, dict):
        raise ValueError("myhome_detail_data_shape")
    stmt = data.get("statement")
    if not isinstance(stmt, dict):
        raise ValueError("myhome_detail_statement_shape")
    return stmt


class MyHomeEnricher:
    """HTTP-детализация лида (очередь: нет адреса или нет ``price_gel``)."""

    def __init__(
        self,
        repository: LeadRepository,
        *,
        base_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._repository = repository
        self._base_url = base_url
        self._client = client

    def enrich_leads(self, leads: Iterable[Lead]) -> MyHomeEnrichReport:
        report = MyHomeEnrichReport()
        items = list(leads)
        if not items:
            return report
        own_client = self._client is None
        client = self._client or httpx.Client()
        try:
            for lead in items:
                err = self._enrich_one(client, lead)
                if err is None:
                    report.enriched += 1
                else:
                    report.failed += 1
                    report.errors.append(err)
        finally:
            if own_client:
                client.close()
        return report

    def _enrich_one(self, client: httpx.Client, lead: Lead) -> str | None:
        lid = str(lead.id) if lead.id else "none"
        label = f"source=myhome id={lid} ext={lead.external_id}"
        try:
            if lead.id is None:
                return f"no_lead_id:{lead.external_id}"
            stmt = fetch_statement_detail(
                client,
                base_url=self._base_url,
                external_id=lead.external_id,
            )
            updates = statement_to_lead_updates(stmt)
            merged = lead.model_copy(update=updates)
            self._repository.update_enriched_fields(merged)
        except Exception as exc:
            logger.warning(
                "myhome api enrich fail %s type=%s",
                label,
                type(exc).__name__,
            )
            return f"{lead.external_id}:{type(exc).__name__}"
        return None


def enrich_leads_via_api(
    repository: LeadRepository,
    leads: Iterable[Lead],
    *,
    base_url: str,
    client: httpx.Client | None = None,
) -> MyHomeEnrichReport:
    """Функциональный фасад для тестов."""
    return MyHomeEnricher(repository, base_url=base_url, client=client).enrich_leads(leads)
