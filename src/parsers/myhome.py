from __future__ import annotations

import httpx

from domain.lead import Lead
from parsers.adapters.myhome.parser import (
    MyHomeRunReport,
    fetch_raw_list_batch,
    parse_list_item,
    run_list_pipeline,
)
from parsers.base import BaseParser
from repositories.base import LeadRepository

__all__ = ["MyHomeParser", "MyHomeRunReport"]


class MyHomeParser(BaseParser):
    """Парсер списка объявлений myhome.ge (HTTP API); реализация — ``adapters.myhome.parser``."""

    SOURCE = "myhome"

    def __init__(
        self,
        client: httpx.AsyncClient,
        repository: LeadRepository,
        *,
        base_url: str | None = None,
    ) -> None:
        self._client = client
        self._repository = repository
        self._base_url = (base_url or "https://api-statements.tnet.ge").rstrip("/")

    async def fetch_raw_batch(self) -> list[dict]:
        return await fetch_raw_list_batch(self._client, base_url=self._base_url)

    async def parse_lead(self, raw: dict) -> Lead | None:
        return parse_list_item(raw, source=self.SOURCE)

    async def run(self) -> MyHomeRunReport:
        return await run_list_pipeline(
            self._client,
            self._repository,
            base_url=self._base_url,
            source=self.SOURCE,
        )
