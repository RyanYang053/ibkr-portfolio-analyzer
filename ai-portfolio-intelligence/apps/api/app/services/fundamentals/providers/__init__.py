from __future__ import annotations

import sys

from app.core.config import settings
from app.services.fundamentals.mock_provider import MockFundamentalProvider


def get_fundamental_provider(allow_mock: bool | None = None) -> MockFundamentalProvider:
    if allow_mock is None:
        allow_mock = settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
    return MockFundamentalProvider(allow_mock=allow_mock)
