from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.rate_limit import (
    _client_ip,
    _rate_limit_keys,
    check_login_allowed,
    clear_login_failures,
    record_login_failure,
)


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str, headers: dict[str, str] | None = None) -> None:
        self.client = _FakeClient(host)
        self.headers = headers or {}


def test_rate_limit_keys_include_account_ip_and_combined():
    request = _FakeRequest("203.0.113.10")
    keys = _rate_limit_keys(request, "Owner@Example.com")
    assert keys == [
        "account:owner@example.com",
        "ip:203.0.113.10",
        "ip_email:203.0.113.10:owner@example.com",
    ]


def test_client_ip_ignores_forwarded_header_without_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.1"])
    request = _FakeRequest("203.0.113.10", {"x-forwarded-for": "198.51.100.5, 203.0.113.10"})
    assert _client_ip(request) == "203.0.113.10"


def test_client_ip_honors_forwarded_header_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.1"])
    request = _FakeRequest("127.0.0.1", {"x-forwarded-for": "198.51.100.5, 127.0.0.1"})
    assert _client_ip(request) == "198.51.100.5"


def test_check_login_allowed_blocks_locked_account_key(monkeypatch):
    monkeypatch.setattr("app.core.rate_limit._table_available", lambda: False)
    locked_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    monkeypatch.setattr(
        "app.core.rate_limit._load_persistent_state",
        lambda key: type("State", (), {"failures": 5, "locked_until": datetime.fromisoformat(locked_until)})()
        if key.startswith("account:")
        else None,
    )

    request = _FakeRequest("127.0.0.1")
    with pytest.raises(HTTPException) as exc:
        check_login_allowed(request, "owner@example.com")
    assert exc.value.status_code == 429


def test_check_login_allowed_blocks_locked_ip_key(monkeypatch):
    monkeypatch.setattr("app.core.rate_limit._table_available", lambda: False)
    locked_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    monkeypatch.setattr(
        "app.core.rate_limit._load_persistent_state",
        lambda key: type("State", (), {"failures": 5, "locked_until": datetime.fromisoformat(locked_until)})()
        if key.startswith("ip:")
        else None,
    )

    request = _FakeRequest("198.51.100.5")
    with pytest.raises(HTTPException) as exc:
        check_login_allowed(request, "owner@example.com")
    assert exc.value.status_code == 429


def test_record_login_failure_upserts_all_keys(monkeypatch):
    executed: list[dict] = []

    class FakeSession:
        def execute(self, statement, params=None):
            executed.append({"sql": str(statement), "params": params or {}})
            return MagicMock()

        def commit(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.core.rate_limit._table_available", lambda: True)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(settings, "login_max_attempts", 5)
    monkeypatch.setattr(settings, "login_lockout_minutes", 15)

    request = _FakeRequest("127.0.0.1")
    record_login_failure(request, "owner@example.com")

    assert len(executed) == 3
    assert all("ON CONFLICT (client_key)" in entry["sql"] for entry in executed)
    assert executed[0]["params"]["key"] == "account:owner@example.com"
    assert executed[1]["params"]["key"] == "ip:127.0.0.1"
    assert executed[2]["params"]["key"] == "ip_email:127.0.0.1:owner@example.com"


def test_clear_login_failures_deletes_all_keys(monkeypatch):
    executed: list[dict] = []

    class FakeSession:
        def execute(self, statement, params=None):
            executed.append({"sql": str(statement), "params": params or {}})
            return MagicMock()

        def commit(self) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.core.rate_limit._table_available", lambda: True)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: FakeSession())

    request = _FakeRequest("127.0.0.1")
    clear_login_failures(request, "owner@example.com")

    assert len(executed) == 1
    assert executed[0]["params"]["keys"] == [
        "account:owner@example.com",
        "ip:127.0.0.1",
        "ip_email:127.0.0.1:owner@example.com",
    ]

@pytest.mark.skipif(
    os.getenv("PERSISTENCE_BACKEND") != "postgres" or not os.getenv("DATABASE_URL"),
    reason="Postgres login rate limit integration requires DATABASE_URL and PERSISTENCE_BACKEND=postgres",
)
def test_postgres_login_rate_limit_locks_after_max_attempts(monkeypatch):
    from sqlalchemy import text

    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "login_max_attempts", 3)
    monkeypatch.setattr(settings, "login_lockout_minutes", 15)

    key = "account:integration-test@example.com"
    with SessionLocal() as session:
        session.execute(text("DELETE FROM login_rate_limits WHERE client_key = :key"), {"key": key})
        session.commit()

    request = _FakeRequest("127.0.0.1")
    for _ in range(3):
        record_login_failure(request, "integration-test@example.com")

    with pytest.raises(HTTPException) as exc:
        check_login_allowed(request, "integration-test@example.com")
    assert exc.value.status_code == 429

    clear_login_failures(request, "integration-test@example.com")
