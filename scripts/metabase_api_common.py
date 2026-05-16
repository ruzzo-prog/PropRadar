"""Общие вызовы Metabase HTTP API для скриптов автоматизации дашбордов."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

_LOGGER = logging.getLogger("metabase_api_common")

_MAP_VISUALIZATION_SETTINGS: dict[str, Any] = {
    "map.type": "pin",
    "map.latitude_column": "latitude",
    "map.longitude_column": "longitude",
}


@dataclass(frozen=True)
class DashcardSpec:
    card_id: int
    row: int
    col: int
    size_x: int
    size_y: int
    series_card_ids: tuple[int, ...] = ()


def login_session(client: httpx.Client, *, user: str, password: str) -> None:
    sess = client.post("/api/session", json={"username": user, "password": password})
    if sess.status_code >= 400:
        msg = f"Ошибка входа Metabase (код {sess.status_code})"
        raise RuntimeError(msg)
    token = sess.json().get("id")
    if not token:
        msg = "В ответе /api/session нет id токена"
        raise RuntimeError(msg)
    client.headers["X-Metabase-Session"] = str(token)


def find_database_id(client: httpx.Client, name: str) -> int:
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


def list_dashboards(client: httpx.Client) -> list[dict[str, Any]]:
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


def find_dashboard_id(client: httpx.Client, name: str) -> int | None:
    for d in list_dashboards(client):
        if d.get("name") == name and d.get("id") is not None:
            return int(d["id"])
    r = client.get("/api/search", params={"models": "dashboard", "q": name[:32]})
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


def get_dashboard(client: httpx.Client, dashboard_id: int) -> dict[str, Any]:
    gr = client.get(f"/api/dashboard/{dashboard_id}")
    gr.raise_for_status()
    dash = gr.json()
    if not isinstance(dash, dict):
        msg = "Ответ GET /api/dashboard не объект JSON"
        raise RuntimeError(msg)
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


def _next_dashcard_id(dashcards: list[dict[str, Any]]) -> int:
    ids = [
        int(dc["id"])
        for dc in dashcards
        if isinstance(dc, dict) and isinstance(dc.get("id"), int)
    ]
    return (min(ids) - 1) if ids else -1


def visualization_settings_for_display(display: str) -> dict[str, Any]:
    if display == "map":
        return dict(_MAP_VISUALIZATION_SETTINGS)
    return {}


def native_card_body(
    *,
    database_id: int,
    name: str,
    description: str | None,
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
        "visualization_settings": visualization_settings_for_display(display),
    }


def create_native_card(
    client: httpx.Client,
    *,
    database_id: int,
    name: str,
    description: str | None,
    sql_text: str,
    display: str,
) -> int:
    body = native_card_body(
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


def delete_card(client: httpx.Client, card_id: int) -> None:
    r = client.delete(f"/api/card/{card_id}")
    if r.status_code >= 400 and r.status_code != 404:
        raise RuntimeError(f"DELETE /api/card/{card_id}: {r.text[:300]}")


def delete_dashboard_and_cards(client: httpx.Client, dashboard_name: str) -> None:
    dashboard_id = find_dashboard_id(client, dashboard_name)
    if dashboard_id is None:
        return
    dash = get_dashboard(client, dashboard_id)
    for dc in _dashcards_list(dash):
        if not isinstance(dc, dict):
            continue
        raw_cid = dc.get("card_id")
        if raw_cid is not None:
            delete_card(client, int(raw_cid))
        for series_item in dc.get("series") or []:
            if not isinstance(series_item, dict):
                continue
            sid = series_item.get("id")
            if sid is not None:
                delete_card(client, int(sid))
    dr = client.delete(f"/api/dashboard/{dashboard_id}")
    if dr.status_code >= 400 and dr.status_code != 404:
        raise RuntimeError(f"DELETE /api/dashboard/{dashboard_id}: {dr.text[:300]}")
    _LOGGER.info("Удалён дашборд «%s» id=%s", dashboard_name, dashboard_id)


def create_dashboard(client: httpx.Client, name: str) -> int:
    dr = client.post("/api/dashboard", json={"name": name, "parameters": []})
    if dr.status_code >= 400:
        raise RuntimeError(f"POST /api/dashboard: {dr.text[:500]}")
    dashboard_id = dr.json().get("id")
    if not isinstance(dashboard_id, int):
        msg = "Ответ POST /api/dashboard без id"
        raise RuntimeError(msg)
    return dashboard_id


def put_dashboard_dashcards(
    client: httpx.Client,
    dashboard_id: int,
    layout: list[DashcardSpec],
) -> None:
    dash = get_dashboard(client, dashboard_id)
    tab_id = _dashboard_tab_id(dash)
    dashcards: list[dict[str, Any]] = []
    nid = -1
    for spec in layout:
        series_payload = [
            {"id": sid, "model": "card"} for sid in spec.series_card_ids
        ]
        dc: dict[str, Any] = {
            "id": nid,
            "card_id": spec.card_id,
            "row": spec.row,
            "col": spec.col,
            "size_x": spec.size_x,
            "size_y": spec.size_y,
            "parameter_mappings": [],
            "series": series_payload,
            "visualization_settings": {},
        }
        if tab_id is not None:
            dc["dashboard_tab_id"] = tab_id
        dashcards.append(dc)
        nid -= 1
    dash["dashcards"] = dashcards
    pr = client.put(f"/api/dashboard/{dashboard_id}", json=dash)
    if pr.status_code >= 400:
        raise RuntimeError(f"PUT /api/dashboard/{dashboard_id}: {pr.text[:500]}")
