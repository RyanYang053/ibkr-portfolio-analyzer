"""Release E2: portfolio options risk endpoint + persistence (§11)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_portfolio_options_endpoint_and_snapshot():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        res = client.get("/portfolio/options?account_id=MOCK-001")
        assert res.status_code == 200
        body = res.json()
        assert body["order_generated"] is False
        assert "net_greeks" in body
        assert "snapshot_id" in body
        assert body["data_quality"]["status"] in {"available", "no_options"}
        # Exclusions are surfaced, not hidden.
        assert isinstance(body["exclusions"], list)
    finally:
        settings.broker_mode = orig
