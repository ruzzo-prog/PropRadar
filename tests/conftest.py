"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_ids_snapshot_module_state() -> None:
    """Изолировать in-process флаг refresh между unit-тестами."""
    import api.ids_snapshot as mod

    with mod._refresh_state_lock:
        mod._refreshing = False
        mod._last_error = None
    yield
    with mod._refresh_state_lock:
        mod._refreshing = False
        mod._last_error = None
