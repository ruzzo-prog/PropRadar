"""Снимок myhome_statement_json и parse_list_item rooms."""

from __future__ import annotations

from parsers.adapters.myhome.enricher import (
    statement_to_lead_updates,
    strip_html_comment_to_plain_text,
)
from parsers.adapters.myhome.parser import parse_list_item
from parsers.adapters.myhome.statement_snapshot import (
    parse_room_value,
    prepare_statement_snapshot,
    resolve_rooms,
)

_DROP_KEYS = {
    "nearby_places",
    "gifts",
    "price_label",
    "point",
    "parameters",
    "youtube_link",
    "has_color",
    "is_old",
    "is_promoted",
    "is_super_vip",
    "is_vip",
    "is_vip_plus",
    "dynamic_slug",
    "3d_url",
    "map_static_image",
}


def test_parse_room_value_int_and_string() -> None:
    assert parse_room_value(3) == 3
    assert parse_room_value("2") == 2
    assert parse_room_value("x") is None
    assert parse_room_value(None) is None


def test_resolve_rooms_prefers_room_over_room_type_id() -> None:
    assert resolve_rooms(room="2", room_type_id=4) == 2


def test_resolve_rooms_from_room_type_id() -> None:
    assert resolve_rooms(room=None, room_type_id=4) == 4
    assert resolve_rooms(room_type_id=0) is None
    assert resolve_rooms() is None


def test_parse_list_item_maps_room_to_leads_rooms() -> None:
    lead = parse_list_item(
        {
            "id": 99,
            "uuid": "64e53fa9-e0dc-4538-a19b-46125f08b4ae",
            "price": {"1": {"price_total": 100}},
            "room": "2",
        },
    )
    assert lead is not None
    assert lead.rooms == 2


def test_parse_list_item_maps_room_type_id_to_leads_rooms() -> None:
    lead = parse_list_item(
        {
            "id": 100,
            "uuid": "64e53fa9-e0dc-4538-a19b-46125f08b4ae",
            "price": {"1": {"price_total": 100}},
            "room_type_id": 4,
        },
    )
    assert lead is not None
    assert lead.rooms == 4


def test_prepare_statement_snapshot_images_and_drops() -> None:
    stmt = {
        "address": "Street",
        "comment": "A<br />B",
        "nearby_places": {"x": 1},
        "parameters": [],
        "images": [
            {"thumb": "t1", "blur": "b1", "large": "L1", "is_main": False},
            {"thumb": "t2", "blur": "b2", "large": "L2", "is_main": True},
        ],
    }
    snap = prepare_statement_snapshot(stmt, strip_comment_html=strip_html_comment_to_plain_text)
    assert snap["address"] == "Street"
    assert snap["comment"] == "A\nB"
    assert _DROP_KEYS.isdisjoint(snap.keys())
    imgs = snap["images"]
    assert len(imgs) == 2
    assert imgs[0]["thumb"] == "t2"
    assert "large" not in imgs[0]
    assert "is_main" not in imgs[0]
    assert set(imgs[0].keys()) <= {"thumb", "blur"}


def test_statement_to_lead_updates_sanitized_json() -> None:
    stmt = {
        "id": 1,
        "room_type_id": 2,
        "comment": "<p>x</p>",
        "gifts": [1],
        "price": {},
        "images": [{"thumb": "t", "large": "bad"}],
    }
    upd = statement_to_lead_updates(stmt)
    snap = upd["myhome_statement_json"]
    assert "gifts" not in snap
    assert "room_type_id" in snap
    assert upd["rooms"] == 2
    assert snap["comment"] == "x"
    assert "large" not in snap["images"][0]
