"""Маппинг detail statement API → поля Lead."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from uuid import UUID

from parsers.adapters.myhome.enricher import (
    statement_to_lead_updates,
    strip_html_comment_to_plain_text,
)
from parsers.adapters.myhome.pdf import resolve_pdf_url


def test_statement_to_lead_updates_maps_core_fields() -> None:
    stmt = {
        "id": 24619471,
        "uuid": "64e53fa9-e0dc-4538-a19b-46125f08b4ae",
        "price": {
            "1": {"price_total": 726000, "price_square": 12737},
            "2": {"price_total": 274370, "price_square": 4813},
        },
        "address": "Test street 1",
        "district_name": "Vake",
        "comment": "Nice flat",
        "area": 57,
        "floor": 9,
        "total_floors": 15,
        "lat": 44.781676,
        "lng": 41.794785,
        "views": 373,
        "is_owner": True,
        "created_at": "2026-05-02 23:21:16",
        "parameters": [],
    }
    upd = statement_to_lead_updates(stmt)
    assert upd["price_gel"] == 726000
    assert upd["price_usd"] == 274370
    assert upd["price_m2_usd"] == 4813
    assert upd["source_listing_uuid"] == UUID("64e53fa9-e0dc-4538-a19b-46125f08b4ae")
    assert upd["address"] == "Test street 1"
    assert upd["address_lang"] == "ka"
    assert upd["district"] == "Vake"
    assert upd["district_lang"] == "ka"
    assert upd["description"] == "Nice flat"
    assert upd["description_lang"] == "ka"
    assert upd["area_m2"] == Decimal("57")
    assert upd["floor"] == "9/15"
    assert upd["geo_lat"] == Decimal("44.781676")
    assert upd["geo_lng"] == Decimal("41.794785")
    assert upd["listing_views"] == 373
    assert upd["is_owner"] is True
    assert upd["published_at"] is not None
    assert upd["published_at"].tzinfo == UTC
    snap = upd["myhome_statement_json"]
    assert isinstance(snap, dict)
    assert "parameters" not in snap


def test_statement_to_lead_updates_strips_comment_html() -> None:
    stmt = {
        "id": 1,
        "comment": "Линия 1.<br /><br /><p>Линия 2</p>",
        "price": {},
    }
    upd = statement_to_lead_updates(stmt)
    assert upd["description"] == "Линия 1.\nЛиния 2"
    assert upd["myhome_statement_json"]["comment"] == "Линия 1.\nЛиния 2"


def test_strip_html_comment_idempotent_plain_text() -> None:
    t = "Обычный текст без разметки"
    assert strip_html_comment_to_plain_text(t) == t
    assert strip_html_comment_to_plain_text(strip_html_comment_to_plain_text(t)) == t


def test_resolve_pdf_url_local_prefix() -> None:
    assert resolve_pdf_url(external_id="42", public_base=None) == "local:42.pdf"


def test_resolve_pdf_url_public_prefix() -> None:
    u = resolve_pdf_url(external_id="7", public_base="https://cdn.example/base/")
    assert u == "https://cdn.example/base/7.pdf"
