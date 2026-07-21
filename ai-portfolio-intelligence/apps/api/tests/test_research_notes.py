"""Release C2: structured research notes (§8.5)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_research_notes_crud_and_versioning():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        created = client.post(
            "/research/notes",
            json={
                "account_id": "MOCK-001",
                "instrument_id": "MSFT:1",
                "symbol": "MSFT",
                "note_type": "earnings",
                "title": "Q1 read",
                "body": "Margins expanded.",
                "tags": ["margins"],
            },
        )
        assert created.status_code == 200
        nid = created.json()["note_id"]
        assert created.json()["version"] == 1

        # Update bumps the version.
        updated = client.patch(f"/research/notes/{nid}", json={"body": "Margins expanded materially."})
        assert updated.status_code == 200
        assert updated.json()["version"] == 2

        listed = client.get("/research/notes?account_id=MOCK-001").json()
        assert listed["count"] >= 1
        by_instrument = client.get("/research/notes?account_id=MOCK-001&instrument_id=MSFT:1").json()
        assert all(n["instrument_id"] == "MSFT:1" for n in by_instrument["notes"])

        fetched = client.get(f"/research/notes/{nid}")
        assert fetched.status_code == 200
        assert fetched.json()["note_type"] == "earnings"

        assert client.get("/research/notes/nope").status_code == 404
    finally:
        settings.broker_mode = orig
