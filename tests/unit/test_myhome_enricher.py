from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from domain.lead import Lead, LeadStatus
from parsers.exceptions import SessionExpiredError
from parsers.myhome_enricher import (
    MyHomeEnricher,
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
    """
    d = extract_details_from_page_text(text)
    assert d["address"] is not None and "Руставели" in str(d["address"])
    assert d["district"] is not None and "Ваке" in str(d["district"])
    assert d["area_m2"] == pytest.approx(65.5)
    assert d["rooms"] == 3
    assert d["floor"] == "4/9"
    assert d["is_owner"] is True


def test_parse_phone_401_raises_session_expired() -> None:
    resp = MagicMock()
    resp.status = 401
    resp.json.return_value = {}
    with pytest.raises(SessionExpiredError):
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

    def list_pending_enrichment(self, source: str, *, limit: int) -> list[Lead]:
        return []

    def update_enriched_fields(self, entity: Lead) -> Lead:
        self.updates.append(entity)
        self.by_id[entity.id] = entity  # type: ignore[index]
        return entity


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
    )
    merged = lead.model_copy(
        update={
            "phone": "500000000",
            "address": details.get("address"),
            "district": details.get("district"),
            "area_m2": Decimal("55"),
            "rooms": details.get("rooms"),
            "floor": details.get("floor"),
            "description": details.get("description"),
            "is_owner": bool(details.get("is_owner")),
        },
    )
    out = repo.update_enriched_fields(merged)
    assert out.phone == "500000000"
    assert len(repo.updates) == 1
    assert repo.updates[0].area_m2 == Decimal("55")


def test_enricher_missing_session_file_raises(tmp_path) -> None:
    repo = _MemRepo()
    missing = tmp_path / "no_session.json"
    enricher = MyHomeEnricher(repo, session_storage_path=missing)
    with pytest.raises(SessionExpiredError):
        enricher.enrich_leads([])
