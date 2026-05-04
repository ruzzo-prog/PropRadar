"""Автонастройка дашборда Metabase «PropRadar — Лиды» через HTTP API.

Требуются переменные окружения:
  METABASE_URL       — например http://localhost:3031
  METABASE_USER      — email/логин администратора
  METABASE_PASSWORD  — пароль (не логировать)
  LEADS_DATABASE_NAME — опционально, по умолчанию «PropRadar Leads»

Идемпотентность: если дашборд с таким именем уже есть — WARNING и exit 0.
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
_LOGGER = logging.getLogger("setup_metabase_dashboard")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_bundle() -> dict[str, Any]:
    path = _repo_root() / "metabase" / "propradar_dashboard.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


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


def _card_by_title(bundle: dict[str, Any], title: str) -> dict[str, Any]:
    for c in bundle.get("cards", []):
        if isinstance(c, dict) and c.get("title_ru") == title:
            return c
    msg = f"В propradar_dashboard.json нет карточки «{title}»"
    raise KeyError(msg)


def _create_native_card(
    client: httpx.Client,
    *,
    database_id: int,
    name: str,
    description: str,
    sql_text: str,
    display: str,
) -> int:
    body: dict[str, Any] = {
        "name": name,
        "description": description,
        "dataset_query": {
            "type": "native",
            "native": {"query": sql_text, "template-tags": {}},
            "database": database_id,
        },
        "display": display,
        "visualization_settings": {},
    }
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


def _add_dashcard(
    client: httpx.Client,
    dashboard_id: int,
    card_id: int,
    row: int,
    col: int,
    size_x: int,
    size_y: int,
) -> None:
    payload: dict[str, Any] = {
        "cardId": card_id,
        "row": row,
        "col": col,
        "sizeX": size_x,
        "sizeY": size_y,
        "parameter_mappings": [],
        "visualization_settings": {},
    }
    r = client.post(f"/api/dashboard/{dashboard_id}/cards", json=payload)
    if r.status_code < 400:
        return
    # fallback: альтернативные имена полей (старые/другие сборки)
    alt = {
        "card_id": card_id,
        "row": row,
        "col": col,
        "size_x": size_x,
        "size_y": size_y,
        "parameter_mappings": [],
        "visualization_settings": {},
    }
    r2 = client.post(f"/api/dashboard/{dashboard_id}/cards", json=alt)
    if r2.status_code < 400:
        return
    _LOGGER.error("POST /api/dashboard/.../cards failed: %s / %s", r.text[:300], r2.text[:300])
    raise RuntimeError("Не удалось добавить карточку на дашборд (см. логи выше)")


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

        existing = _find_dashboard_id(client, DASHBOARD_NAME)
        if existing is not None:
            _LOGGER.warning(
                "Дашборд «%s» уже существует (id=%s). Повторное создание пропущено.",
                DASHBOARD_NAME,
                existing,
            )
            return 0

        database_id = _find_database_id(client, db_name)
        _LOGGER.info("Используется база Metabase id=%s name=%s", database_id, db_name)

        titles_order = [
            "Лиды сегодня",
            "Новых за 7 дней",
            "Средняя цена объекта (USD)",
            "Воронка лидов",
            "Лиды по дням",
            "Последние лиды",
        ]
        card_ids: dict[str, int] = {}
        for title in titles_order:
            spec = _card_by_title(bundle, title)
            sql_text = str(spec["sql"])
            display = str(spec.get("display", "table"))
            desc = str(spec.get("description_ru", ""))
            cid = _create_native_card(
                client,
                database_id=database_id,
                name=title,
                description=desc,
                sql_text=sql_text,
                display=display,
            )
            card_ids[title] = cid
            _LOGGER.info("Создана карточка «%s» id=%s", title, cid)

        dash_body = {"name": DASHBOARD_NAME, "parameters": []}
        dr = client.post("/api/dashboard", json=dash_body)
        if dr.status_code >= 400:
            _LOGGER.error("Создание дашборда: %s", dr.text[:500])
            return 1
        dashboard_id = dr.json().get("id")
        if not isinstance(dashboard_id, int):
            _LOGGER.error("Ответ POST /api/dashboard без id")
            return 1
        _LOGGER.info("Создан дашборд «%s» id=%s", DASHBOARD_NAME, dashboard_id)

        layout: list[tuple[str, int, int, int, int]] = [
            ("Лиды сегодня", 0, 0, 4, 3),
            ("Новых за 7 дней", 0, 4, 4, 3),
            ("Средняя цена объекта (USD)", 0, 8, 4, 3),
            ("Воронка лидов", 3, 0, 6, 4),
            ("Лиды по дням", 3, 6, 6, 4),
            ("Последние лиды", 7, 0, 12, 8),
        ]
        for title, row, col, sx, sy in layout:
            _add_dashcard(client, dashboard_id, card_ids[title], row, col, sx, sy)
            _LOGGER.info("На дашборд добавлена «%s» row=%s col=%s", title, row, col)

    _LOGGER.info("Готово. Откройте Metabase и проверьте дашборд «%s».", DASHBOARD_NAME)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyError, OSError, json.JSONDecodeError, httpx.HTTPError) as exc:
        logging.getLogger("setup_metabase_dashboard").error("%s: %s", type(exc).__name__, exc)
        raise SystemExit(1) from exc
