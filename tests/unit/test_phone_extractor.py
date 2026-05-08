"""Юнит-тесты HTTP-first извлечения телефона myhome.ge (без Playwright)."""

from __future__ import annotations

import httpx
import pytest

from parsers.adapters.myhome.phone_extractor import extract_phone_from_listing_html, get_phone


def test_extract_from_next_data_nested() -> None:
    html = (
        '<html><head></head><body>'
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"statement":{"phone_number":"555123456"}}}}'
        "</script></body></html>"
    )
    assert extract_phone_from_listing_html(html) == "555123456"


def test_extract_from_json_ld_telephone() -> None:
    html = (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","telephone":"+995 555 123 456"}'
        "</script></body></html>"
    )
    assert extract_phone_from_listing_html(html) == "995555123456"


def test_next_data_priority_over_ld_json() -> None:
    html = (
        "<html>"
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"a":{"phone_number":"111222333"}}'
        "</script>"
        '<script type="application/ld+json">'
        '{"telephone":"+995999888777"}'
        "</script>"
        "</html>"
    )
    assert extract_phone_from_listing_html(html) == "111222333"


def test_malformed_next_data_fallback_to_ld_json() -> None:
    html = (
        "<html>"
        '<script id="__NEXT_DATA__" type="application/json">NOT_JSON</script>'
        '<script type="application/ld+json">'
        '{"telephone":"566777888"}'
        "</script>"
        "</html>"
    )
    assert extract_phone_from_listing_html(html) == "566777888"


def test_no_phone_returns_none() -> None:
    html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"title":"x"}}}'
        "</script></html>"
    )
    assert extract_phone_from_listing_html(html) is None


def test_short_digit_string_rejected() -> None:
    html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        '{"phone_number":"12345"}'
        "</script></html>"
    )
    assert extract_phone_from_listing_html(html) is None


@pytest.mark.asyncio
async def test_get_phone_200_returns_digits() -> None:
    snippet = '{"props":{"pageProps":{"x":{"mobile":"591234567"}}}}'
    body = (
        f"<html><script id=\"__NEXT_DATA__\" type=\"application/json\">{snippet}</script></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/ru/pr/42/" in str(request.url)
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        phone = await get_phone("42", client, locale="ru")
    assert phone == "591234567"


@pytest.mark.asyncio
async def test_get_phone_http_error_returns_none() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        assert await get_phone("7", client) is None


@pytest.mark.asyncio
async def test_get_phone_non_200_returns_none() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        assert await get_phone("7", client) is None


@pytest.mark.asyncio
async def test_get_phone_empty_statement_id() -> None:

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200, text="")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        assert await get_phone("  ", client) is None
        assert await get_phone("", client) is None
