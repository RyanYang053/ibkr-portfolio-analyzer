from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import account_access_store, user_store
from app.api.deps import get_broker_adapter
from app.core.security import create_access_token
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter


@pytest.fixture
def chat_client(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.disable_auth_enforcement", False)
    monkeypatch.setattr("app.core.config.settings.broker_mode", "mock_ibkr_readonly")
    monkeypatch.setattr(
        user_store,
        "_USERS",
        {
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
        {"viewer@example.com": ["MOCK-001"]},
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

    adapter = MockIBKRAdapter()
    app.dependency_overrides[get_broker_adapter] = lambda: adapter
    token = create_access_token("viewer@example.com", role="viewer")
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client, adapter
    app.dependency_overrides.clear()


def test_chat_rejects_unauthorized_account_before_broker_position_read(chat_client):
    client, adapter = chat_client
    get_positions = MagicMock(side_effect=adapter.get_positions)
    adapter.get_positions = get_positions

    response = client.post(
        "/ai/chat?account_id=MOCK-002",
        json={"message": "Analyze MSFT", "tagged_symbols": ["MSFT"], "history": []},
    )

    assert response.status_code == 403
    get_positions.assert_not_called()


def test_chat_uses_authorized_account_for_tagged_context(chat_client):
    client, adapter = chat_client
    calls: list[str] = []

    def tracked_get_positions(account_id: str):
        calls.append(account_id)
        return adapter.get_positions(account_id)

    adapter.get_positions = tracked_get_positions

    response = client.post(
        "/ai/chat?account_id=MOCK-001",
        json={"message": "Analyze MSFT", "tagged_symbols": ["MSFT"], "history": []},
    )

    assert response.status_code == 200
    assert calls
    assert all(account_id == "MOCK-001" for account_id in calls)


def test_chat_multi_account_without_selection_returns_422_before_context_reads(chat_client):
    client, adapter = chat_client
    account_access_store._ACCESS["viewer@example.com"] = ["MOCK-001", "MOCK-002"]

    get_positions = MagicMock(side_effect=adapter.get_positions)
    adapter.get_positions = get_positions

    response = client.post(
        "/ai/chat",
        json={"message": "Analyze MSFT", "tagged_symbols": ["MSFT"], "history": []},
    )

    assert response.status_code == 422
    get_positions.assert_not_called()
