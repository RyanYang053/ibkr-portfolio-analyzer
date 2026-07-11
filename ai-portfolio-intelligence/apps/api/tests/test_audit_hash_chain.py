from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.core.audit import get_audit_logs, log_audit_action
from app.core.config import settings
from app.db.audit_event_repo import (
    _canonical_event_json,
    _compute_event_hash,
    _redact_mapping,
    insert_audit_event,
    verify_audit_chain,
)


def test_redact_mapping_masks_configured_sensitive_keys():
    payload = {
        "email": "owner@example.com",
        "password": "secret-password",
        "nested": {"api_key": "abc123", "role": "owner"},
    }
    redacted = _redact_mapping(payload)
    assert redacted["email"] == "owner@example.com"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["role"] == "owner"


def test_event_hash_links_previous_event():
    occurred_at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    canonical_first = _canonical_event_json(
        occurred_at=occurred_at,
        actor_type="user",
        actor_id="owner@example.com",
        tenant_id="owner@example.com",
        account_id="MOCK-001",
        action="user_invited",
        object_type="user",
        object_id="viewer@example.com",
        request_id="req-1",
        source_ip="127.0.0.1",
        outcome="success",
        before={},
        after={"role": "viewer"},
        metadata={"invited_by": "owner@example.com"},
    )
    first_hash = _compute_event_hash("", canonical_first)

    canonical_second = _canonical_event_json(
        occurred_at=datetime(2026, 7, 10, 12, 1, tzinfo=timezone.utc),
        actor_type="user",
        actor_id="owner@example.com",
        tenant_id="owner@example.com",
        account_id="MOCK-001",
        action="account_access_granted",
        object_type="account",
        object_id="MOCK-001",
        request_id="req-2",
        source_ip="127.0.0.1",
        outcome="success",
        before={},
        after={},
        metadata={"email": "viewer@example.com"},
    )
    second_hash = _compute_event_hash(first_hash, canonical_second)

    assert first_hash == hashlib.sha256(canonical_first.encode("utf-8")).hexdigest()
    assert second_hash == hashlib.sha256(f"{first_hash}{canonical_second}".encode("utf-8")).hexdigest()
    assert first_hash != second_hash


def test_verify_audit_chain_detects_tampered_event(monkeypatch):
    occurred_at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    class FakeRow(dict):
        pass

    rows = [
        FakeRow(
            id="evt-1",
            occurred_at=occurred_at,
            actor_type="user",
            actor_id="owner@example.com",
            tenant_id="owner@example.com",
            account_id=None,
            action="user_invited",
            object_type="user",
            object_id="viewer@example.com",
            request_id=None,
            source_ip="127.0.0.1",
            outcome="success",
            before_json={},
            after_json={},
            metadata_json={},
            previous_event_hash=None,
            event_hash="tampered-hash",
        )
    ]

    class FakeSession:
        def execute(self, *_args, **_kwargs):
            return MagicMockMappings(rows)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class MagicMockMappings:
        def __init__(self, values):
            self._values = values

        def mappings(self):
            return self

        def all(self):
            return self._values

    monkeypatch.setattr("app.db.audit_event_repo.audit_events_available", lambda: True)
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: FakeSession())

    result = verify_audit_chain()
    assert result["valid"] is False
    assert result["reason"] == "event_hash_mismatch"


def test_get_audit_logs_returns_empty_in_production_without_events(monkeypatch):
    monkeypatch.setattr("app.core.audit.audit_events_available", lambda: False)
    monkeypatch.setattr(settings, "persistence_backend", "json")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr("app.core.audit.read_json_with_legacy", lambda *_args, **_kwargs: None)

    assert get_audit_logs() == []


def test_critical_audit_action_fails_when_persistence_fails(monkeypatch):
    def _raise_insert(**_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.core.audit.audit_events_available", lambda: True)
    monkeypatch.setattr("app.core.audit.insert_audit_event", _raise_insert)

    with pytest.raises(RuntimeError, match="Critical audit event persistence failed"):
        log_audit_action(
            action="user_invited",
            object_type="user",
            object_id="viewer@example.com",
            actor_id="owner@example.com",
            critical=True,
        )


@pytest.mark.skipif(
    os.getenv("PERSISTENCE_BACKEND") != "postgres" or not os.getenv("DATABASE_URL"),
    reason="Postgres audit hash chain integration requires DATABASE_URL and PERSISTENCE_BACKEND=postgres",
)
def test_postgres_audit_chain_and_immutability(monkeypatch):
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "persistence_backend", "postgres")

    insert_audit_event(
        action="hash_chain_test",
        object_type="test",
        object_id="one",
        actor_type="user",
        actor_id="owner@example.com",
        tenant_id="owner@example.com",
        account_id="MOCK-001",
        request_id=None,
        source_ip="127.0.0.1",
        outcome="success",
        before={"password": "secret"},
        after={"role": "viewer"},
        metadata={"token": "abc"},
    )
    insert_audit_event(
        action="hash_chain_test",
        object_type="test",
        object_id="two",
        actor_type="user",
        actor_id="owner@example.com",
        tenant_id="owner@example.com",
        account_id="MOCK-001",
        request_id=None,
        source_ip="127.0.0.1",
        outcome="success",
        before={},
        after={},
        metadata={},
    )

    verification = verify_audit_chain()
    assert verification["valid"] is True
    assert verification["count"] >= 2

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT before_json, after_json, metadata_json
                FROM audit_events
                WHERE action = 'hash_chain_test' AND object_id = 'one'
                ORDER BY occurred_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()
        assert row is not None
        assert row["before_json"]["password"] == "[REDACTED]"
        assert row["metadata_json"]["token"] == "[REDACTED]"

        with pytest.raises(Exception, match="immutable"):
            session.execute(
                text("UPDATE audit_events SET outcome = 'tampered' WHERE action = 'hash_chain_test'")
            )
            session.commit()
