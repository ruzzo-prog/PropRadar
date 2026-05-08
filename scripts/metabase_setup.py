"""Заливка дашборда PropRadar в Metabase через HTTP API (requests).

Переменные окружения:
  METABASE_URL              — базовый URL, например http://178.104.79.236:3031
  METABASE_ADMIN_EMAIL      — логин администратора (email)
  METABASE_ADMIN_PASSWORD   — пароль (не логировать)

Источник: metabase/propradar_dashboard.json
Имя дашборда: поле dashboard_title_ru из bundle.

Идемпотентность: если дашборд с таким именем уже существует — INFO и exit 0.

Запуск: python3 scripts/metabase_setup.py
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

_LOGGER = logging.getLogger("metabase_setup")

# Сетка Metabase: size_x, size_y в колонках/строках (24 колонки). Ключ — position из JSON.
_LAYOUT_SIZE: dict[int, tuple[int, int]] = {
    1: (12, 8),  # bar
    2: (6, 4),
    3: (6, 4),
    4: (6, 4),
    5: (6, 4),
    6: (24, 8),  # line
    7: (24, 12),  # table
    8: (6, 4),
    9: (12, 8),  # bar
    10: (6, 4),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_bundle() -> dict[str, Any]:
    path = _repo_root() / "metabase" / "propradar_dashboard.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _parse_database_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [x for x in payload["data"] if isinstance(x, dict)]
    return []


def _db_score(db: dict[str, Any]) -> tuple[int, int]:
    """Меньше = лучше. Возвращает (ранг, id) для сортировки."""
    raw_id = db.get("id")
    db_id = int(raw_id) if raw_id is not None else 999999
    name = str(db.get("name") or "").lower()
    engine = str(db.get("engine") or "").lower()
    details = db.get("details") if isinstance(db.get("details"), dict) else {}
    db_name_in_details = ""
    if isinstance(details, dict):
        db_name_in_details = str(details.get("db") or details.get("dbname") or "").lower()

    haystack = f"{name} {db_name_in_details}"

    if "propradar" in name:
        return (0, db_id)
    if "propradar" in haystack:
        return (1, db_id)
    if "lead" in haystack and engine == "postgres":
        return (2, db_id)
    if "lead" in name and engine == "postgres":
        return (3, db_id)
    if engine == "postgres":
        return (10, db_id)
    return (100, db_id)


def _pick_database_id(databases: list[dict[str, Any]]) -> tuple[int, str]:
    if not databases:
        raise RuntimeError("Список баз Metabase пуст (GET /api/database).")
    scored = sorted(databases, key=_db_score)
    best = scored[0]
    rank = _db_score(best)[0]
    if rank >= 100:
        raise RuntimeError(
            "Не найдена подходящая БД (ожидался postgres с PropRadar или leads в имени). "
            "Проверьте подключения в Metabase Admin."
        )
    bid = best.get("id")
    if bid is None:
        raise RuntimeError("У выбранной базы нет поля id.")
    return int(bid), str(best.get("name") or "")


def _list_dashboards(sess: requests.Session, base: str) -> list[dict[str, Any]]:
    r = sess.get(f"{base}/api/dashboard", timeout=60)
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


def _find_dashboard_id(sess: requests.Session, base: str, name: str) -> int | None:
    for d in _list_dashboards(sess, base):
        if d.get("name") == name:
            raw_id = d.get("id")
            if raw_id is not None:
                return int(raw_id)
    r = sess.get(
        f"{base}/api/search",
        params={"models": "dashboard", "q": name[:32]},
        timeout=60,
    )
    if r.status_code >= 400:
        return None
    body = r.json()
    if not isinstance(body, dict):
        return None
    for item in body.get("data", []):
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


def _layout_positions() -> dict[int, tuple[int, int, int, int]]:
    """row, col, size_x, size_y — без пересечений, сетка 24 колонки."""
    # row 0: bar 1 + bar 9 (высота 8)
    p1 = (0, 0, *_LAYOUT_SIZE[1])
    p9 = (0, 12, *_LAYOUT_SIZE[9])
    # row 8: scalar 2–5
    y0 = 8
    p2 = (y0, 0, *_LAYOUT_SIZE[2])
    p3 = (y0, 6, *_LAYOUT_SIZE[3])
    p4 = (y0, 12, *_LAYOUT_SIZE[4])
    p5 = (y0, 18, *_LAYOUT_SIZE[5])
    # row 12: line 6 (высота 8)
    y1 = y0 + 4  # 12
    p6 = (y1, 0, *_LAYOUT_SIZE[6])
    # row 20: table 7 (высота 12)
    y2 = y1 + 8  # 20
    p7 = (y2, 0, *_LAYOUT_SIZE[7])
    # row 32: scalar 8, 10
    y3 = y2 + 12  # 32
    p8 = (y3, 0, *_LAYOUT_SIZE[8])
    p10 = (y3, 6, *_LAYOUT_SIZE[10])
    return {1: p1, 2: p2, 3: p3, 4: p4, 5: p5, 6: p6, 7: p7, 8: p8, 9: p9, 10: p10}


def _create_native_card(
    sess: requests.Session,
    base: str,
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
    r = sess.post(f"{base}/api/card", json=body, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(
            f"Metabase отклонил POST /api/card «{name}»: HTTP {r.status_code} — {r.text[:500]}"
        )
    created = r.json()
    cid = created.get("id")
    if not isinstance(cid, int):
        raise RuntimeError("Ответ POST /api/card без числового id")
    return cid


def _try_post_dashboard_cards(
    sess: requests.Session,
    base: str,
    dashboard_id: int,
    layout: list[tuple[int, int, int, int, int]],
) -> bool:
    """POST /api/dashboard/:id/cards — если маршрут есть и принимает тело, True."""
    url = f"{base}/api/dashboard/{dashboard_id}/cards"
    payload = [
        {
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": sx,
            "size_y": sy,
        }
        for card_id, row, col, sx, sy in layout
    ]
    r = sess.post(url, json=payload, timeout=120)
    if r.status_code == 404:
        _LOGGER.info("POST %s → 404, используем PUT /api/dashboard/%s", url, dashboard_id)
        return False
    if r.status_code >= 400:
        _LOGGER.info(
            "POST %s → HTTP %s, fallback на PUT /api/dashboard/%s",
            url,
            r.status_code,
            dashboard_id,
        )
        return False
    _LOGGER.info("Карточки добавлены через POST %s", url)
    return True


def _put_dashboard_dashcards(
    sess: requests.Session,
    base: str,
    dashboard_id: int,
    layout: list[tuple[int, int, int, int, int]],
) -> None:
    gr = sess.get(f"{base}/api/dashboard/{dashboard_id}", timeout=60)
    gr.raise_for_status()
    dash = gr.json()
    if not isinstance(dash, dict):
        raise RuntimeError("Ответ GET /api/dashboard не объект JSON")
    existing = dash.get("dashcards")
    if not isinstance(existing, list):
        oc = dash.get("ordered_cards")
        existing = oc if isinstance(oc, list) else []
    tab_id: int | None = None
    tabs = dash.get("tabs")
    if isinstance(tabs, list) and tabs and isinstance(tabs[0], dict):
        raw = tabs[0].get("id")
        if raw is not None:
            tab_id = int(raw)
    new_cards: list[dict[str, Any]] = []
    nid = -1
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
        new_cards.append(dc)
        nid -= 1
    dash["dashcards"] = existing + new_cards
    pr = sess.put(f"{base}/api/dashboard/{dashboard_id}", json=dash, timeout=120)
    if pr.status_code >= 400:
        raise RuntimeError(
            f"PUT /api/dashboard/{dashboard_id} не удалось: HTTP {pr.status_code} — {pr.text[:500]}"
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    base = os.environ.get("METABASE_URL", "").rstrip("/")
    user = os.environ.get("METABASE_ADMIN_EMAIL", "")
    password = os.environ.get("METABASE_ADMIN_PASSWORD", "")

    if not base or not user or not password:
        _LOGGER.error(
            "Задайте METABASE_URL, METABASE_ADMIN_EMAIL, METABASE_ADMIN_PASSWORD в окружении."
        )
        return 1

    _LOGGER.info("Шаг: загрузка bundle из metabase/propradar_dashboard.json")
    bundle = _load_bundle()
    dashboard_title = str(bundle.get("dashboard_title_ru") or "").strip()
    if not dashboard_title:
        _LOGGER.error("В bundle отсутствует непустой dashboard_title_ru.")
        return 1
    _LOGGER.info("Шаг: имя дашборда из bundle: %s", dashboard_title)

    sess = requests.Session()

    _LOGGER.info("Шаг: POST /api/session")
    sess_resp = sess.post(
        f"{base}/api/session",
        json={"username": user, "password": password},
        timeout=60,
    )
    if sess_resp.status_code >= 400:
        _LOGGER.error("Ошибка входа Metabase: HTTP %s", sess_resp.status_code)
        return 1
    token = sess_resp.json().get("id")
    if not token:
        _LOGGER.error("В ответе /api/session нет поля id (токен сессии).")
        return 1
    sess.headers["X-Metabase-Session"] = str(token)
    _LOGGER.info("Шаг: сессия получена (токен не логируется).")

    _LOGGER.info("Шаг: GET /api/database")
    db_resp = sess.get(f"{base}/api/database", timeout=60)
    if db_resp.status_code >= 400:
        _LOGGER.error("GET /api/database: HTTP %s", db_resp.status_code)
        return 1
    databases = _parse_database_list(db_resp.json())
    try:
        database_id, db_name = _pick_database_id(databases)
    except RuntimeError as exc:
        _LOGGER.error("%s", exc)
        return 1
    _LOGGER.info("Шаг: выбрана база id=%s name=%s", database_id, db_name)

    _LOGGER.info("Шаг: проверка существующего дашборда «%s»", dashboard_title)
    existing_id = _find_dashboard_id(sess, base, dashboard_title)
    if existing_id is not None:
        _LOGGER.info(
            "Дашборд уже существует (id=%s). Повторное создание не выполняется.",
            existing_id,
        )
        return 0

    card_specs = _sorted_bundle_cards(bundle)
    _LOGGER.info("Шаг: в bundle карточек: %s", len(card_specs))

    geom_by_pos = _layout_positions()
    card_ids_by_position: dict[int, int] = {}
    for spec in card_specs:
        try:
            pos = int(spec["position"])
        except (KeyError, TypeError, ValueError) as exc:
            _LOGGER.error("Карточка без корректного position: %s", exc)
            return 1
        if pos not in geom_by_pos:
            _LOGGER.error("Нет раскладки для position=%s в _LAYOUT_SIZE/_layout_positions", pos)
            return 1
        title = str(spec.get("title_ru", f"position_{pos}"))
        _LOGGER.info("Шаг: создание карточки position=%s title=%s", pos, title)
        sql_text = str(spec["sql"])
        display = str(spec.get("display", "table"))
        desc = str(spec.get("description_ru", ""))
        try:
            cid = _create_native_card(
                sess,
                base,
                database_id=database_id,
                name=title,
                description=desc,
                sql_text=sql_text,
                display=display,
            )
        except RuntimeError as exc:
            _LOGGER.error("%s", exc)
            return 1
        card_ids_by_position[pos] = cid
        _LOGGER.info("Шаг: карточка создана id=%s", cid)

    _LOGGER.info("Шаг: POST /api/dashboard")
    dr = sess.post(
        f"{base}/api/dashboard",
        json={"name": dashboard_title, "parameters": []},
        timeout=60,
    )
    if dr.status_code >= 400:
        _LOGGER.error("Создание дашборда: HTTP %s — %s", dr.status_code, dr.text[:500])
        return 1
    dashboard_id = dr.json().get("id")
    if not isinstance(dashboard_id, int):
        _LOGGER.error("Ответ POST /api/dashboard без числового id.")
        return 1
    _LOGGER.info("Шаг: дашборд создан id=%s", dashboard_id)

    layout_payload: list[tuple[int, int, int, int, int]] = []
    for pos in sorted(card_ids_by_position.keys()):
        row, col, sx, sy = geom_by_pos[pos]
        cid = card_ids_by_position[pos]
        layout_payload.append((cid, row, col, sx, sy))
        _LOGGER.info(
            "Шаг: привязка карточки id=%s position=%s → row=%s col=%s size_x=%s size_y=%s",
            cid,
            pos,
            row,
            col,
            sx,
            sy,
        )

    _LOGGER.info("Шаг: привязка карточек к дашборду")
    if not _try_post_dashboard_cards(sess, base, dashboard_id, layout_payload):
        _put_dashboard_dashcards(sess, base, dashboard_id, layout_payload)
        _LOGGER.info("Шаг: карточки записаны через PUT /api/dashboard/%s", dashboard_id)

    _LOGGER.info("Готово. Дашборд «%s» id=%s", dashboard_title, dashboard_id)
    return 0


if __name__ == "__main__":
    _main_errors = (
        RuntimeError,
        KeyError,
        OSError,
        json.JSONDecodeError,
        requests.RequestException,
    )
    try:
        raise SystemExit(main())
    except _main_errors as exc:
        _LOGGER.error("%s: %s", type(exc).__name__, exc)
        raise SystemExit(1) from exc
