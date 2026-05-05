"""Pydantic-схемы адаптера myhome."""

from __future__ import annotations

from parsers.adapters.myhome.schema import MyHomeListItem, MyHomeStatementPayload


def test_list_item_accepts_extra_keys() -> None:
    raw = {"id": 1, "uuid": None, "dynamic_title": "x", "parameters": []}
    m = MyHomeListItem.model_validate(raw)
    assert m.id == 1


def test_statement_payload_validates_id() -> None:
    raw = {"id": 42, "unknown_future_field": True}
    m = MyHomeStatementPayload.model_validate(raw)
    assert m.id == 42
