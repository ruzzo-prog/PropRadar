"""Подготовка dict для сохранения в ``leads.myhome_statement_json``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_DROP_KEYS = frozenset(
    {
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
    },
)

_IMAGE_KEEP_KEYS = frozenset({"thumb", "blur"})


def parse_room_value(room: Any) -> int | None:
    """Число комнат из list/detail поля ``room`` (int или цифровая строка)."""
    if isinstance(room, int):
        return room
    if isinstance(room, str) and room.strip().isdigit():
        return int(room.strip())
    return None


def _normalize_images(images: Any) -> list[dict[str, Any]]:
    if not isinstance(images, list):
        return []
    dict_items = [x for x in images if isinstance(x, dict)]
    sorted_items = sorted(dict_items, key=lambda item: (0 if item.get("is_main") is True else 1))
    out: list[dict[str, Any]] = []
    for item in sorted_items:
        slim = {k: item[k] for k in _IMAGE_KEEP_KEYS if k in item}
        if slim:
            out.append(slim)
    return out


def prepare_statement_snapshot(
    statement: dict[str, Any],
    *,
    strip_comment_html: Callable[[str], str],
) -> dict[str, Any]:
    """Копия statement для JSONB: без мусорных ключей, усечённые images, чистый comment."""
    out = {k: v for k, v in statement.items() if k not in _DROP_KEYS}
    if "images" in out:
        out["images"] = _normalize_images(statement.get("images"))
    comment = out.get("comment")
    if isinstance(comment, str) and comment.strip():
        out["comment"] = strip_comment_html(comment)
    return out
