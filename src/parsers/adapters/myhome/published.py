"""Разбор published_at: локаль Asia/Tbilisi → UTC (избегаем неоднозначных случаев)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

TBILISI = ZoneInfo("Asia/Tbilisi")

# Фрагмент после маркера публикации (одна «осмысленная» дата на блок)
_PUB_HEAD = re.compile(
    r"(?:გამოქვეყნდა|გამოქრდა|Published|Опубликовано?|Опубликован|Posted|Размещен[оа]?|"
    r"დაიდო|დადო|Updated|Обновлено?)\s*[:\s-]*",
    re.I,
)


def _normalize_snippet(text: str) -> str:
    line = text.split("\n", 1)[0].strip()
    return re.sub(r"\s+", " ", line)[:120]


def parse_published_at_from_text(
    text: str,
    *,
    reference: datetime | None = None,
) -> datetime | None:
    """Вернуть timezone-aware UTC или None при неоднозначности/ошибке."""
    m = _PUB_HEAD.search(text)
    if not m:
        return None
    tail = text[m.end() : m.end() + 160]
    snippet = _normalize_snippet(tail)

    ref = reference if reference is not None else datetime.now(TBILISI)
    if ref.tzinfo is None:
        ref_local = ref.replace(tzinfo=TBILISI)
    else:
        ref_local = ref.astimezone(TBILISI)
    base_date = ref_local.date()

    candidates: list[datetime] = []

    today_m = re.search(
        r"(?:Сегодня|Today|დღეს)[,.\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?",
        snippet,
        re.I,
    )
    yesterday_m = re.search(
        r"(?:Вчера|Вчора|Yesterday|გუშინ)[,.\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?",
        snippet,
        re.I,
    )
    abs_m = re.search(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})[,\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?",
        snippet,
    )

    if today_m:
        h, mi = int(today_m.group(1)), int(today_m.group(2))
        candidates.append(datetime(
            base_date.year, base_date.month, base_date.day, h, mi, 0, tzinfo=TBILISI))
    if yesterday_m:
        h, mi = int(yesterday_m.group(1)), int(yesterday_m.group(2))
        yd = base_date - timedelta(days=1)
        candidates.append(datetime(yd.year, yd.month, yd.day, h, mi, 0, tzinfo=TBILISI))
    if abs_m:
        d, mo, y = int(abs_m.group(1)), int(abs_m.group(2)), int(abs_m.group(3))
        h, mi = int(abs_m.group(4)), int(abs_m.group(5))
        try:
            candidates.append(datetime(y, mo, d, h, mi, 0, tzinfo=TBILISI))
        except ValueError:
            return None

    if len(candidates) != 1:
        return None
    return candidates[0].astimezone(UTC)
