import pytest
from fastapi.testclient import TestClient

from app.api import account_access_store, user_store
from app.api.deps import get_broker_adapter
from app.core.security import create_access_token
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter


@pytest.fixture
def isolated_client(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.disable_auth_enforcement", False)
    monkeypatch.setattr("app.core.config.settings.broker_mode", "mock_ibkr_readonly")
    monkeypatch.setattr(
        user_store,
        "_USERS",
        {
            "owner@example.com": {
                "email": "owner@example.com",
                "name": "Owner",
                "password_hash": "x",
                "role": "owner",
                "token_version": "0",
            },
            "viewer@example.com": {
                "email": "viewer@example.com",
                "name": "Viewer",
                "password_hash": "x",
                "role": "viewer",
                "token_version": "0",
            },
        },
    )
    monkeypatch.setattr(
        account_access_store,
        "_ACCESS",
        {
            "owner@example.com": ["*"],
            "viewer@example.com": ["MOCK-001"],
        },
    )
    monkeypatch.setattr(user_store, "_hydrate_users", lambda: None)
    monkeypatch.setattr(account_access_store, "_hydrate", lambda: None)
    monkeypatch.setattr(
        account_access_store,
        "list_accessible_accounts",
        lambda email: list(account_access_store._ACCESS.get(email.lower(), [])),
    )
    monkeypatch.setattr(
        account_access_store,
        "user_has_account_access",
        lambda email, account_id: account_id in account_access_store._ACCESS.get(email.lower(), []),
    )

    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    token = create_access_token("viewer@example.com", role="viewer")
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client
    app.dependency_overrides.clear()


def test_viewer_cannot_read_other_account_summary(isolated_client):
    response = isolated_client.get("/portfolio/summary?account_id=MOCK-002")
    assert response.status_code == 403


def test_viewer_can_read_granted_account(isolated_client):
    response = isolated_client.get("/portfolio/summary?account_id=MOCK-001")
    assert response.status_code == 200
