"""Проверка JSON-bundle для create_metabase_dashboards.py (без сети)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from create_metabase_dashboards import _build_layout, _load_bundle  # noqa: E402


def test_monitoring_bundle_layout_and_series() -> None:
    bundle = _load_bundle("monitoring_admin_dashboard.json")
    assert bundle["dashboard_name"] == "PropRadar — Мониторинг"
    cards = bundle["cards"]
    assert len(cards) == 11
    ids = {str(c["key"]): 1000 + i for i, c in enumerate(cards)}
    layout = _build_layout(cards, ids)
    assert len(layout) == 10
    chart = next(dc for dc in layout if dc.card_id == ids["synced_by_day"])
    assert chart.series_card_ids == (ids["published_by_day"],)


def test_map_bundle_scalars_and_map_layout() -> None:
    bundle = _load_bundle("map_objects_dashboard.json")
    assert bundle["dashboard_name"] == "PropRadar — Карта объектов"
    cards = bundle["cards"]
    assert len(cards) == 3
    ids = {str(c["key"]): 100 + i for i, c in enumerate(cards)}
    layout = _build_layout(cards, ids)
    assert len(layout) == 3
    map_card = next(c for c in cards if c["key"] == "map")
    assert map_card["visualization_settings"]["map.latitude_column"] == "longitude"
    map_tile = next(dc for dc in layout if dc.card_id == ids["map"])
    assert map_tile.row == 1 and map_tile.size_x == 12


def test_monitoring_latest_leads_sql_fixes() -> None:
    bundle = _load_bundle("monitoring_admin_dashboard.json")
    latest = next(c for c in bundle["cards"] if c["key"] == "latest_leads")
    sql = latest["sql"]
    assert "myhome_statement_json->>'condition'" in sql
    assert "CASE" in sql and "TRIM(lc.floor)" in sql
    assert "JOIN leads l" in sql


def test_bundles_are_valid_json() -> None:
    root = Path(__file__).resolve().parents[2] / "metabase"
    for name in ("monitoring_admin_dashboard.json", "map_objects_dashboard.json"):
        data = json.loads((root / name).read_text(encoding="utf-8"))
        assert isinstance(data.get("cards"), list)
