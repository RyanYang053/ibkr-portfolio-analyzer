"""Release F2: persisted onboarding state machine (§21)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.onboarding import ONBOARDING_STAGES


def test_onboarding_state_defaults_and_persistence():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        state = client.get("/onboarding/state")
        assert state.status_code == 200
        body = state.json()
        assert len(body["stages"]) == len(ONBOARDING_STAGES)
        assert body["persistence"] == "sqlite"  # not localStorage
        assert body["complete"] is False
        assert body["readiness"]["overall"] == 0.0

        # Complete a portfolio-data stage -> readiness updates and persists.
        upd = client.put("/onboarding/stages/account_discovery", json={"status": "complete"})
        assert upd.status_code == 200
        assert upd.json()["completed_at"] is not None

        readiness = client.get("/onboarding/readiness").json()["readiness"]
        assert readiness["portfolio_data"] > 0.0
        assert readiness["overall"] > 0.0

        # Unknown stage is rejected.
        assert client.put("/onboarding/stages/nope", json={"status": "complete"}).status_code == 404
    finally:
        settings.broker_mode = orig
