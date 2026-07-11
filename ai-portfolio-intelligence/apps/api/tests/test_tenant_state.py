import pytest
from fastapi.testclient import TestClient

from app.api import account_access_store, user_store
from app.api.deps import get_broker_adapter
from app.core.security import create_access_token
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter


@pytest.fixture
def tenant_client(monkeypatch):
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
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_watchlist_items_are_user_scoped(tenant_client, monkeypatch):
    from app.services import watchlist_store

    monkeypatch.setattr(watchlist_store, "_load_watchlist_for_user", lambda user_id: [])
    monkeypatch.setattr(watchlist_store, "_save_watchlist_for_user", lambda user_id, items: None)

    owner_headers = {"Authorization": f"Bearer {create_access_token('owner@example.com', role='owner')}"}
    viewer_headers = {"Authorization": f"Bearer {create_access_token('viewer@example.com', role='viewer')}"}

    saved: dict[str, list[dict]] = {}

    def fake_load(user_id: str) -> list[dict]:
        return list(saved.get(user_id, []))

    def fake_save(user_id: str, items: list[dict]) -> None:
        saved[user_id] = list(items)

    monkeypatch.setattr(watchlist_store, "load_user_watchlist", fake_load)
    monkeypatch.setattr(watchlist_store, "save_user_watchlist", fake_save)

    created = tenant_client.post(
        "/watchlist",
        headers=owner_headers,
        json={"symbol": "AAPL", "reason": "owner watch"},
    )
    assert created.status_code == 200

    viewer_list = tenant_client.get("/watchlist", headers=viewer_headers)
    assert viewer_list.status_code == 200
    assert viewer_list.json() == []

    owner_list = tenant_client.get("/watchlist", headers=owner_headers)
    assert owner_list.json()[0]["symbol"] == "AAPL"


def test_stock_route_denies_unauthorized_account_position(tenant_client):
    viewer_headers = {"Authorization": f"Bearer {create_access_token('viewer@example.com', role='viewer')}"}
    response = tenant_client.get("/stocks/MSFT?account_id=MOCK-002", headers=viewer_headers)
    assert response.status_code == 403
