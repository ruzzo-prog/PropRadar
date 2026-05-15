"""Автонастройка дашборда Metabase «PropRadar — Лиды» через HTTP API.

Требуются переменные окружения:
  METABASE_URL       — например http://localhost:3031
  METABASE_USER      — email/логин администратора
  METABASE_PASSWORD  — пароль (не логировать)
  LEADS_DATABASE_NAME — опционально, по умолчанию «PropRadar Leads»

Режимы:
  - Дашборда нет: создаются все карточки из bundle (позиции 1–11) и дашборд.
  - Дашборд есть: идемпотентно обновляются только карточки position 7 и 11
    (PUT /api/card/:id или создание + добавление на дашборд).

SQL и типы карточек читаются из metabase/propradar_dashboard.json.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

DASHBOARD_NAME = "PropRadar — Лиды"
_MANAGED_POSITIONS = frozenset({7, 11})
_LOGGER = logging.getLogger("setup_metabase_dashboard")

# Сетка дашборда (row, col, size_x, size_y), 12 колонок; ключ — position из propradar_dashboard.json
_LAYOUT_BY_POSITION: dict[int, tuple[int, int, int, int]] = {
    1: (3, 0, 6, 4),
    2: (0, 0, 4, 3),
    3: (0, 4, 4, 3),
    4: (0, 8, 4, 3),
    5: (1, 0, 4, 3),
    6: (3, 6, 6, 4),
    7: (7, 0, 12, 8),
    8: (15, 0, 4, 3),
    9: (16, 0, 12, 4),
    10: (15, 4, 4, 3),
    11: (20, 0, 12, 10),
}

_MAP_VISUALIZATION_SETTINGS: dict[str, Any] = {
    "map.type": "pin",
    "map.latitude_column": "latitude",
    "map.longitude_column": "longitude",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_bundle() -> dict[str, Any]:
    path = _repo_root() / "metabase" / "propradar_dashboard.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _card_spec_by_position(bundle: dict[str, Any], position: int) -> dict[str, Any]:
    for spec in bundle.get("cards", []):
        if not isinstance(spec, dict):
            continue
        try:
            pos = int(spec.get("position", 0))
        except (TypeError, ValueError):
            continue
        if pos == position:
            return spec
    msg = f"В bundle нет карточки position={position}"
    raise KeyError(msg)


def _sorted_bundle_cards(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw = bundle.get("cards", [])
    if not isinstance(raw, list):
        return []
    items: list[tuple[int, dict[str, Any]]] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        try:
            pos = int(c.get("position", 0))
        except (TypeError, ValueError):
            continue
        items.append((pos, c))
    items.sort(key=lambda t: t[0])
    return [c for _, c in items]


def _list_dashboards(client: httpx.Client) -> list[dict[str, Any]]:
    r = client.get("/api/dashboard")
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("data", "dashboards", "items"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def _find_dashboard_id(client: httpx.Client, name: str) -> int | None:
    for d in _list_dashboards(client):
        if d.get("name") == name:
            raw_id = d.get("id")
            if raw_id is not None:
                return int(raw_id)
    r = client.get(
        "/api/search",
        params={
            "models": "dashboard",
            "q": name[:32],
        },
    )
    if r.status_code >= 400:
        return None
    for item in r.json().get("data", []):
        if not isinstance(item, dict):
            continue
        if item.get("model") != "dashboard":
            continue
        if item.get("name") != name:
            continue
        raw_id = item.get("id")
        if raw_id is not None:
            return int(raw_id)
    return None


def _find_database_id(client: httpx.Client, name: str) -> int:
    r = client.get("/api/database")
    r.raise_for_status()
    payload = r.json()
    databases: list[dict[str, Any]] = []
    if isinstance(payload, list):
        databases = [x for x in payload if isinstance(x, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        databases = [x for x in payload["data"] if isinstance(x, dict)]

    for db in databases:
        if db.get("name") == name and db.get("id") is not None:
            return int(db["id"])
    msg = (
        f"База Metabase с именем «{name}» не найдена. "
        "Добавьте её в UI или проверьте LEADS_DATABASE_NAME."
    )
    raise RuntimeError(msg)


def _visualization_settings_for_display(display: str) -> dict[str, Any]:
    if display == "map":
        return dict(_MAP_VISUALIZATION_SETTINGS)
    return {}


def _native_card_body(
    *,
    database_id: int,
    name: str,
    description: str,
    sql_text: str,
    display: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "dataset_query": {
            "type": "native",
            "native": {"query": sql_text, "template-tags": {}},
            "database": database_id,
        },
        "display": display,
        "visualization_settings": _visualization_settings_for_display(display),
    }


def _create_native_card(
    client: httpx.Client,
    *,
    database_id: int,
    name: str,
    description: str,
    sql_text: str,
    display: str,
) -> int:
    body = _native_card_body(
        database_id=database_id,
        name=name,
        description=description,
        sql_text=sql_text,
        display=display,
    )
    r = client.post("/api/card", json=body)
    if r.status_code >= 400:
        _LOGGER.error("Metabase отклонил создание карточки «%s»: %s", name, r.status_code)
        raise RuntimeError(r.text[:500])
    created = r.json()
    cid = created.get("id")
    if not isinstance(cid, int):
        msg = "Ответ POST /api/card без числового id"
        raise RuntimeError(msg)
    return cid


def _update_native_card(
    client: httpx.Client,
    card_id: int,
    *,
    database_id: int,
    name: str,
    description: str,
    sql_text: str,
    display: str,
) -> None:
    gr = client.get(f"/api/card/{card_id}")
    if gr.status_code >= 400:
        raise RuntimeError(f"GET /api/card/{card_id}: {gr.text[:300]}")
    card = gr.json()
    if not isinstance(card, dict):
        raise RuntimeError("Ответ GET /api/card не объект")
    card.update(
        _native_card_body(
            database_id=database_id,
            name=name,
            description=description,
            sql_text=sql_text,
            display=display,
        ),
    )
    pr = client.put(f"/api/card/{card_id}", json=card)
    if pr.status_code >= 400:
        _LOGGER.error("PUT /api/card/%s: %s", card_id, pr.text[:500])
        raise RuntimeError(f"Не удалось обновить карточку «{name}»")


def _get_dashboard(client: httpx.Client, dashboard_id: int) -> dict[str, Any]:
    gr = client.get(f"/api/dashboard/{dashboard_id}")
    gr.raise_for_status()
    dash = gr.json()
    if not isinstance(dash, dict):
        raise RuntimeError("Ответ GET /api/dashboard не объект JSON")
    return dash


def _dashcards_list(dash: dict[str, Any]) -> list[dict[str, Any]]:
    existing = dash.get("dashcards")
    if isinstance(existing, list):
        return existing
    oc = dash.get("ordered_cards")
    return oc if isinstance(oc, list) else []


def _dashboard_tab_id(dash: dict[str, Any]) -> int | None:
    tabs = dash.get("tabs")
    if isinstance(tabs, list) and tabs and isinstance(tabs[0], dict):
        raw = tabs[0].get("id")
        if raw is not None:
            return int(raw)
    return None


def _find_card_id_on_dashboard_by_title(
    client: httpx.Client,
    dashboard_id: int,
    title: str,
) -> int | None:
    dash = _get_dashboard(client, dashboard_id)
    for dc in _dashcards_list(dash):
        if not isinstance(dc, dict):
            continue
        raw_cid = dc.get("card_id")
        if raw_cid is None:
            continue
        cid = int(raw_cid)
        cr = client.get(f"/api/card/{cid}")
        if cr.status_code >= 400:
            continue
        card = cr.json()
        if isinstance(card, dict) and card.get("name") == title:
            return cid
    return None


def _next_dashcard_id(dashcards: list[dict[str, Any]]) -> int:
    ids = [int(dc["id"]) for dc in dashcards if isinstance(dc, dict) and isinstance(dc.get("id"), int)]
    return (min(ids) - 1) if ids else -1


def _put_dashboard_dashcards(
    client: httpx.Client,
    dashboard_id: int,
    layout: list[tuple[int, int, int, int, int]],
    *,
    replace: bool = False,
) -> None:
    """Metabase 0.50+: карточки задаются через PUT /api/dashboard/:id (поле dashcards)."""
    dash = _get_dashboard(client, dashboard_id)
    existing = _dashcards_list(dash)
    tab_id = _dashboard_tab_id(dash)
    base = [] if replace else list(existing)
    nid = _next_dashcard_id(base)
    for card_id, row, col, sx, sy in layout:
        dc: dict[str, Any] = {
            "id": nid,
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": sx,
            "size_y": sy,
            "parameter_mappings": [],
            "series": [],
            "visualization_settings": {},
        }
        if tab_id is not None:
            dc["dashboard_tab_id"] = tab_id
        base.append(dc)
        nid -= 1
    dash["dashcards"] = base
    pr = client.put(f"/api/dashboard/{dashboard_id}", json=dash)
    if pr.status_code >= 400:
        _LOGGER.error("PUT /api/dashboard/%s: %s", dashboard_id, pr.text[:500])
        raise RuntimeError("Не удалось обновить дашборд (dashcards)")


def _upsert_managed_card(
    client: httpx.Client,
    *,
    dashboard_id: int,
    database_id: int,
    spec: dict[str, Any],
) -> None:
    pos = int(spec["position"])
    title = str(spec.get("title_ru", f"position_{pos}"))
    sql_text = str(spec["sql"])
    display = str(spec.get("display", "table"))
    desc = str(spec.get("description_ru", ""))

    card_id = _find_card_id_on_dashboard_by_title(client, dashboard_id, title)
    if card_id is not None:
        _LOGGER.info("Обновление карточки «%s» id=%s (PUT)", title, card_id)
        _update_native_card(
            client,
            card_id,
            database_id=database_id,
            name=title,
            description=desc,
            sql_text=sql_text,
            display=display,
        )
        return

    _LOGGER.info("Создание карточки «%s» (position=%s)", title, pos)
    card_id = _create_native_card(
        client,
        database_id=database_id,
        name=title,
        description=desc,
        sql_text=sql_text,
        display=display,
    )
    geom = _LAYOUT_BY_POSITION.get(pos)
    if geom is None:
        raise RuntimeError(f"Нет раскладки для карточки position={pos}")
    row, col, sx, sy = geom
    _put_dashboard_dashcards(client, dashboard_id, [(card_id, row, col, sx, sy)])


def _sync_existing_dashboard(
    client: httpx.Client,
    dashboard_id: int,
    bundle: dict[str, Any],
    database_id: int,
) -> None:
    _LOGGER.info(
        "Дашборд «%s» уже существует (id=%s). Синхронизация карточек %s.",
        DASHBOARD_NAME,
        dashboard_id,
        sorted(_MANAGED_POSITIONS),
    )
    for pos in sorted(_MANAGED_POSITIONS):
        spec = _card_spec_by_position(bundle, pos)
        _upsert_managed_card(
            client,
            dashboard_id=dashboard_id,
            database_id=database_id,
            spec=spec,
        )


def _create_full_dashboard(
    client: httpx.Client,
    bundle: dict[str, Any],
    database_id: int,
) -> int:
    card_specs = _sorted_bundle_cards(bundle)
    _LOGGER.info("В bundle загружено карточек: %s", len(card_specs))

    card_ids_by_position: dict[int, int] = {}
    for spec in card_specs:
        pos = int(spec["position"])
        title = str(spec.get("title_ru", f"position_{pos}"))
        _LOGGER.info("Processing card %s %s", pos, title)
        cid = _create_native_card(
            client,
            database_id=database_id,
            name=title,
            description=str(spec.get("description_ru", "")),
            sql_text=str(spec["sql"]),
            display=str(spec.get("display", "table")),
        )
        card_ids_by_position[pos] = cid
        _LOGGER.info("Создана карточка «%s» (position=%s) id=%s", title, pos, cid)

    dr = client.post("/api/dashboard", json={"name": DASHBOARD_NAME, "parameters": []})
    if dr.status_code >= 400:
        _LOGGER.error("Создание дашборда: %s", dr.text[:500])
        raise RuntimeError("POST /api/dashboard failed")
    dashboard_id = dr.json().get("id")
    if not isinstance(dashboard_id, int):
        raise RuntimeError("Ответ POST /api/dashboard без id")
    _LOGGER.info("Создан дашборд «%s» id=%s", DASHBOARD_NAME, dashboard_id)

    layout_payload: list[tuple[int, int, int, int, int]] = []
    for pos in sorted(card_ids_by_position.keys()):
        geom = _LAYOUT_BY_POSITION.get(pos)
        if geom is None:
            raise RuntimeError(f"Нет раскладки для карточки position={pos}")
        row, col, sx, sy = geom
        layout_payload.append((card_ids_by_position[pos], row, col, sx, sy))
    _put_dashboard_dashcards(client, dashboard_id, layout_payload, replace=True)
    _LOGGER.info("На дашборд добавлено карточек: %s", len(layout_payload))
    return dashboard_id


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    base = os.environ.get("METABASE_URL", "").rstrip("/")
    user = os.environ.get("METABASE_USER", "")
    password = os.environ.get("METABASE_PASSWORD", "")
    db_name = os.environ.get("LEADS_DATABASE_NAME", "PropRadar Leads")

    if not base or not user or not password:
        _LOGGER.error("Задайте METABASE_URL, METABASE_USER, METABASE_PASSWORD в окружении")
        return 1

    bundle = _load_bundle()

    with httpx.Client(base_url=base, timeout=60.0) as client:
        sess = client.post("/api/session", json={"username": user, "password": password})
        if sess.status_code >= 400:
            _LOGGER.error("Ошибка входа Metabase (код %s)", sess.status_code)
            return 1
        token = sess.json().get("id")
        if not token:
            _LOGGER.error("В ответе /api/session нет id токена")
            return 1
        client.headers["X-Metabase-Session"] = str(token)

        database_id = _find_database_id(client, db_name)
        _LOGGER.info("Используется база Metabase id=%s name=%s", database_id, db_name)

        existing = _find_dashboard_id(client, DASHBOARD_NAME)
        if existing is not None:
            _sync_existing_dashboard(client, existing, bundle, database_id)
        else:
            _create_full_dashboard(client, bundle, database_id)

    _LOGGER.info("Готово. Откройте Metabase и проверьте дашборд «%s».", DASHBOARD_NAME)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyError, OSError, json.JSONDecodeError, httpx.HTTPError) as exc:
        logging.getLogger("setup_metabase_dashboard").error("%s: %s", type(exc).__name__, exc)
        raise SystemExit(1) from exc
