from __future__ import annotations

import sys

from app.core.config import settings
from app.services.fundamentals.mock_provider import MockFundamentalProvider


def get_fundamental_provider(allow_mock: bool | None = None) -> MockFundamentalProvider:
    if allow_mock is None:
        allow_mock = settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
    return MockFundamentalProvider(allow_mock=allow_mock)


def fetch_point_in_time_fundamentals(symbol: str, *, allow_mock: bool | None = None) -> dict | None:
    """Return EDGAR-backed fundamentals when configured; otherwise use the mock provider."""
    if allow_mock is None:
        allow_mock = settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
    if not allow_mock:
        from app.services.fundamentals.providers.edgar_provider import fetch_edgar_fundamental_snapshot

        snapshot = fetch_edgar_fundamental_snapshot(symbol)
        if snapshot is not None:
            return snapshot.model_dump()
    provider = get_fundamental_provider(allow_mock=allow_mock)
    snapshot = provider.get_fundamentals(symbol)
    return snapshot.model_dump() if snapshot is not None else None

