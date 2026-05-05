"""Разбор ответа API телефона (без логирования номера)."""

from __future__ import annotations

from playwright.sync_api import Response


def parse_phone_response(response: Response) -> str:
    if response.status == 401:
        raise RuntimeError("phone_api_unauthorized")
    if response.status >= 400:
        msg = f"phone_api_http_{response.status}"
        raise RuntimeError(msg)
    payload = response.json()
    if payload.get("result") is not True:
        raise RuntimeError("phone_api_denied")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("phone_api_shape")
    raw = data.get("phone_number")
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("phone_api_empty")
    return raw.strip()
