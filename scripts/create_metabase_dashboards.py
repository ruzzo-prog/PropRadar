"""Создание дашбордов Metabase «PropRadar — Мониторинг» и «PropRadar — Карта объектов».

Требуются переменные окружения:
  METABASE_URL, METABASE_USER, METABASE_PASSWORD
  LEADS_DATABASE_NAME — опционально, по умолчанию «PropRadar Leads»

Идемпотентность: дашборд с тем же именем удаляется (карточки + дашборд), затем создаётся заново.
Не трогает «PropRadar — Лиды» (scripts/setup_metabase_dashboard.py).

Запуск (только человек, не CI без секретов):
  python scripts/create_metabase_dashboards.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from metabase_api_common import (  # noqa: E402
    DashcardSpec,
    create_dashboard,
    create_native_card,
    delete_dashboard_and_cards,
    find_database_id,
    login_session,
    put_dashboard_dashcards,
)

_LOGGER = logging.getLogger("create_metabase_dashboards")

_BUNDLE_PATHS = (
    "monitoring_admin_dashboard.json",
    "map_objects_dashboard.json",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_bundle(filename: str) -> dict[str, Any]:
    path = _repo_root() / "metabase" / filename
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _dashboard_url(base: str, dashboard_id: int) -> str:
    return f"{base.rstrip('/')}/dashboard/{dashboard_id}"


def _apply_visualization_settings(
    client: httpx.Client,
    card_id: int,
    settings: dict[str, Any],
) -> None:
    gr = client.get(f"/api/card/{card_id}")
    gr.raise_for_status()
    card = gr.json()
    if not isinstance(card, dict):
        msg = f"GET /api/card/{card_id}: не объект"
        raise RuntimeError(msg)
    base = card.get("visualization_settings")
    merged = {**base, **settings} if isinstance(base, dict) else dict(settings)
    card["visualization_settings"] = merged
    pr = client.put(f"/api/card/{card_id}", json=card)
    if pr.status_code >= 400:
        raise RuntimeError(f"PUT /api/card/{card_id}: {pr.text[:500]}")


def _create_cards(
    client: httpx.Client,
    *,
    database_id: int,
    cards: list[dict[str, Any]],
) -> dict[str, int]:
    ids_by_key: dict[str, int] = {}
    for spec in cards:
        key = str(spec["key"])
        title = str(spec["title_ru"])
        display = str(spec.get("display", "table"))
        sql_text = str(spec["sql"])
        desc = spec.get("description_ru") or None
        _LOGGER.info("Создание карточки «%s» (key=%s)", title, key)
        card_id = create_native_card(
            client,
            database_id=database_id,
            name=title,
            description=desc,
            sql_text=sql_text,
            display=display,
        )
        viz = spec.get("visualization_settings")
        if isinstance(viz, dict) and viz:
            _apply_visualization_settings(client, card_id, viz)
        ids_by_key[key] = card_id
    return ids_by_key


def _build_layout(
    cards: list[dict[str, Any]],
    ids_by_key: dict[str, int],
) -> list[DashcardSpec]:
    layout: list[DashcardSpec] = []
    for spec in cards:
        if spec.get("series_only"):
            continue
        layout_raw = spec.get("layout")
        if not isinstance(layout_raw, dict):
            msg = f"Карточка {spec.get('key')}: нет layout"
            raise RuntimeError(msg)
        key = str(spec["key"])
        series_keys = spec.get("series_keys") or []
        series_ids = tuple(ids_by_key[str(k)] for k in series_keys)
        layout.append(
            DashcardSpec(
                card_id=ids_by_key[key],
                row=int(layout_raw["row"]),
                col=int(layout_raw["col"]),
                size_x=int(layout_raw["size_x"]),
                size_y=int(layout_raw["size_y"]),
                series_card_ids=series_ids,
            ),
        )
    return layout


def _provision_dashboard(
    client: httpx.Client,
    bundle: dict[str, Any],
    *,
    database_id: int,
    base_url: str,
) -> tuple[int, str]:
    name = str(bundle["dashboard_name"])
    cards = bundle.get("cards", [])
    if not isinstance(cards, list):
        msg = f"Bundle «{name}»: cards не массив"
        raise RuntimeError(msg)

    delete_dashboard_and_cards(client, name)
    ids_by_key = _create_cards(client, database_id=database_id, cards=cards)
    dashboard_id = create_dashboard(client, name)
    layout = _build_layout(cards, ids_by_key)
    put_dashboard_dashcards(client, dashboard_id, layout)
    url = _dashboard_url(base_url, dashboard_id)
    _LOGGER.info("Дашборд «%s» id=%s карточек на плитках=%s", name, dashboard_id, len(layout))
    return dashboard_id, url


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    base = os.environ.get("METABASE_URL", "").rstrip("/")
    user = os.environ.get("METABASE_USER", "")
    password = os.environ.get("METABASE_PASSWORD", "")
    db_name = os.environ.get("LEADS_DATABASE_NAME", "PropRadar Leads")

    if not base or not user or not password:
        _LOGGER.error("Задайте METABASE_URL, METABASE_USER, METABASE_PASSWORD в окружении")
        return 1

    with httpx.Client(base_url=base, timeout=120.0) as client:
        login_session(client, user=user, password=password)
        database_id = find_database_id(client, db_name)
        _LOGGER.info("База Metabase id=%s name=%s", database_id, db_name)

        results: list[tuple[str, int, str]] = []
        for bundle_file in _BUNDLE_PATHS:
            bundle = _load_bundle(bundle_file)
            dashboard_id, url = _provision_dashboard(
                client,
                bundle,
                database_id=database_id,
                base_url=base,
            )
            results.append((str(bundle["dashboard_name"]), dashboard_id, url))

    for name, did, url in results:
        print(f'Dashboard «{name}» id={did} url={url}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
