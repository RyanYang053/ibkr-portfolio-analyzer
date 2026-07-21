"""Route-level tests for planning goals and construction universe."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_planning_goals_crud(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")
    monkeypatch.setattr(settings, "deployment_mode", "development")
    monkeypatch.setattr(settings, "disable_auth_enforcement", True)

    from app.main import app

    client = TestClient(app)
    # Create plan first
    put = client.put(
        "/planning/plan?plan_id=default",
        json={
            "owner_label": "personal",
            "base_currency": "USD",
            "planning_horizon_years": 10,
            "goals": [],
            "account_roles": [],
            "contribution_plans": [],
            "policy": {"policy_id": "default", "risk_tolerance": "moderate"},
        },
    )
    assert put.status_code == 200
    created = client.post(
        "/planning/goals?plan_id=default",
        json={
            "goal_id": "g1",
            "name": "House",
            "goal_type": "home",
            "target_amount": 100000,
            "currency": "USD",
            "priority": 1,
            "funded_amount": 0,
            "status": "active",
        },
    )
    assert created.status_code == 200
    listed = client.get("/planning/goals?plan_id=default")
    assert listed.status_code == 200
    assert any(g["goal_id"] == "g1" for g in listed.json()["goals"])
    deleted = client.delete("/planning/goals/g1?plan_id=default")
    assert deleted.status_code == 200


def test_replacement_universe_endpoint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")
    monkeypatch.setattr(settings, "deployment_mode", "development")
    monkeypatch.setattr(settings, "disable_auth_enforcement", True)
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")

    from app.main import app

    client = TestClient(app)
    response = client.get("/construction/replacement-universe?account_id=MOCK-001")
    assert response.status_code == 200
    body = response.json()
    assert body["order_generated"] is False
    assert "buy_candidates" in body
    assert "core_etf" in body
