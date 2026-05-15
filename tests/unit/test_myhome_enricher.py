from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from domain.lead import Lead, LeadStatus
from parsers.adapters.myhome.published import TBILISI
from parsers.myhome_enricher import (
    _parse_phone_response,
    extract_details_from_page_text,
    listing_url,
)
from repositories.base import LeadRepository


def test_listing_url_uses_external_id() -> None:
    u = listing_url("12345", locale="ru")
    assert "12345" in u
    assert u.startswith("https://www.myhome.ge/ru/")


def test_extract_details_from_ru_text() -> None:
    text = """
    Адрес: ул. Руставели 10
    Район: Ваке
    Площадь 65.5 м²
    3 комнаты
    Этаж: 4/9
    Я собственник
    Описание: Квартира с видом на город, тихий двор.
    """
    d = extract_details_from_page_text(
        text,
        listing_url="https://www.myhome.ge/ru/pr/1/",
        html_lang="ru-RU",
    )
    assert d["address"] is not None and "Руставели" in str(d["address"])
    assert d["district"] is not None and "Ваке" in str(d["district"])
    assert d["area_m2"] == pytest.approx(65.5)
    assert d["rooms"] == 3
    assert d["floor"] == "4/9"
    assert d["is_owner"] is True
    assert d["description"] is not None and "Квартира" in str(d["description"])
    assert d["address_lang"] == "ru"
    assert d["district_lang"] == "ru"
    assert d["description_lang"] == "ru"


def test_extract_lang_from_url_segment() -> None:
    text = "Адрес: пр. Диди Дигоми 5\nРайон: Дигоми\n45 м²\n"
    d = extract_details_from_page_text(
        text,
        listing_url="https://www.myhome.ge/ka/pr/99/",
        html_lang=None,
    )
    assert d["address_lang"] == "ka"
    assert d["district_lang"] == "ka"


def test_extract_published_today_to_utc() -> None:
    ref = datetime(2026, 5, 5, 15, 0, 0, tzinfo=TBILISI)
    text = "Опубликовано Сегодня, 14:30 что-то ещё"
    d = extract_details_from_page_text(text, published_reference=ref)
    assert d["published_at"] is not None
    dt = d["published_at"]
    assert isinstance(dt, datetime)
    assert dt.tzinfo == UTC
    assert dt.hour == 10  # 14:30 Tbilisi -> 10:30 UTC in May (UTC+4)


def test_extract_published_yesterday_ka() -> None:
    ref = datetime(2026, 5, 5, 12, 0, 0, tzinfo=TBILISI)
    text = "გამოქვეყნდა გუშინ, 09:15"
    d = extract_details_from_page_text(text, published_reference=ref)
    assert d["published_at"] is not None
    dt = d["published_at"]
    expected_local = datetime(2026, 5, 4, 9, 15, 0, tzinfo=TBILISI)
    assert dt == expected_local.astimezone(UTC)


def test_extract_published_ambiguous_returns_none() -> None:
    ref = datetime(2026, 5, 5, 12, 0, 0, tzinfo=TBILISI)
    text = "Опубликовано Сегодня, 10:30, а также Вчера, 11:00"
    d = extract_details_from_page_text(text, published_reference=ref)
    assert d["published_at"] is None


def test_parse_phone_401_raises_unauthorized() -> None:
    resp = MagicMock()
    resp.status = 401
    resp.json.return_value = {}
    with pytest.raises(RuntimeError, match="phone_api_unauthorized"):
        _parse_phone_response(resp)


def test_parse_phone_denied_raises_runtime() -> None:
    resp = MagicMock()
    resp.status = 200
    resp.json.return_value = {"result": False}
    with pytest.raises(RuntimeError, match="phone_api_denied"):
        _parse_phone_response(resp)


def test_parse_phone_success() -> None:
    resp = MagicMock()
    resp.status = 200
    resp.json.return_value = {"result": True, "data": {"phone_number": "551820088"}}
    assert _parse_phone_response(resp) == "551820088"


class _MemRepo(LeadRepository):
    """Минимальная реализация порта для проверки update_enriched_fields."""

    def __init__(self) -> None:
        self.by_id: dict[UUID, Lead] = {}
        self.updates: list[Lead] = []

    def get_by_id(self, entity_id: UUID) -> Lead | None:
        return self.by_id.get(entity_id)

    def save(self, entity: Lead) -> Lead:
        raise NotImplementedError

    def get_by_source_and_external_id(self, source: str, external_id: str) -> Lead | None:
        return None

    def list_pending_detail_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def list_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def claim_pending_phone_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def increment_phone_retry(self, lead_id: UUID) -> int:
        return 1

    def mark_phone_enrich_exhausted(self, lead_id: UUID) -> None:
        return None

    def list_pending_pdf_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def update_enriched_fields(self, entity: Lead) -> Lead:
        self.updates.append(entity)
        self.by_id[entity.id] = entity  # type: ignore[index]
        return entity

    def list_external_ids_by_source_and_status(
        self,
        source: str,
        status: LeadStatus,
    ) -> list[str]:
        return []

    def mark_leads_by_external_ids(
        self,
        source: str,
        external_ids: list[str],
        *,
        status: LeadStatus,
        status_reason: str | None = None,
    ) -> int:
        return 0


def test_repository_update_receives_phone_and_details() -> None:
    repo = _MemRepo()
    lid = uuid4()
    su = uuid4()
    lead = Lead(
        id=lid,
        source="myhome",
        external_id="999",
        status=LeadStatus.NEW,
        score=0,
        source_listing_uuid=su,
    )
    details = extract_details_from_page_text(
        "Адрес: ул. Тест 1\nРайон: Сабуртало\n55 м²\n2 комнаты\nЭтаж: 1/5\n",
        listing_url="https://www.myhome.ge/ru/pr/999/",
        html_lang="ru",
    )
    update: dict[str, object] = {"phone": "500000000"}
    area_val = details.get("area_m2")
    if isinstance(area_val, (int, float)):
        update["area_m2"] = Decimal(str(area_val))
    for key in ("address", "district", "rooms", "floor", "description", "published_at"):
        if (val := details.get(key)) is not None:
            update[key] = val
    for key in ("address_lang", "district_lang", "description_lang"):
        if (val := details.get(key)) is not None:
            update[key] = val
    if details.get("is_owner") is True:
        update["is_owner"] = True
    merged = lead.model_copy(update=update)
    out = repo.update_enriched_fields(merged)
    assert out.phone == "500000000"
    assert len(repo.updates) == 1
    assert repo.updates[0].area_m2 == Decimal("55")
