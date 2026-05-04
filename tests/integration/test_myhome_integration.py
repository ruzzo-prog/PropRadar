from __future__ import annotations

import os

import httpx
import pytest

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_myhome_live_list_endpoint() -> None:
    if os.environ.get("MYHOME_INTEGRATION") != "1":
        pytest.skip("MYHOME_INTEGRATION!=1 (см. .env.example)")
    url = "https://api-statements.tnet.ge/v1/statements/"
    params = {
        "deal_types": 1,
        "real_estate_types": 1,
        "currency_id": 1,
        "cities": 1,
        "owner_type": "physical",
        "page": 1,
        "sort": "date_desc",
    }
    headers = {
        "X-Website-Key": "myhome",
        "Accept": "application/json",
        "Origin": "https://www.myhome.ge",
        "Referer": "https://www.myhome.ge/",
        "User-Agent": _DEFAULT_UA,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers, timeout=60.0)
        response.raise_for_status()
        payload = response.json()
    assert payload.get("result") is True
    data = payload.get("data")
    assert isinstance(data, dict)
    items = data.get("data")
    assert isinstance(items, list)
    assert len(items) > 0
