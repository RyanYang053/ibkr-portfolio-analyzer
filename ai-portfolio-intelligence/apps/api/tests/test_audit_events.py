from __future__ import annotations

from app.core.audit import get_audit_logs, log_audit_action
from app.core.request_context import activate_request_context, clear_request_context


def test_json_audit_events_are_not_truncated_to_100(monkeypatch):
    monkeypatch.setattr("app.core.audit.audit_events_available", lambda: False)
    monkeypatch.setattr("app.core.audit.settings.persistence_backend", "json")

    for index in range(120):
        log_audit_action(
            action=f"test_action_{index}",
            object_type="test",
            object_id=str(index),
            actor_id="tester@example.com",
            account_id="MOCK-001",
            outcome="success",
        )

    logs = get_audit_logs()
    matching = [entry for entry in logs if str(entry.get("object_id", "")).isdigit()]
    assert len(matching) >= 120


def test_audit_event_stores_actor_account_and_request_id(monkeypatch):
    monkeypatch.setattr("app.core.audit.audit_events_available", lambda: False)
    monkeypatch.setattr("app.core.audit.settings.persistence_backend", "json")

    activate_request_context(request_id="req-123", source_ip="127.0.0.1")
    try:
        log_audit_action(
            action="privileged_action",
            object_type="portfolio",
            object_id="MOCK-001",
            actor_id="owner@example.com",
            account_id="MOCK-001",
            outcome="success",
        )
    finally:
        clear_request_context()

    latest = next(entry for entry in get_audit_logs() if entry.get("action") == "privileged_action")
    assert latest["actor_id"] == "owner@example.com"
    assert latest["account_id"] == "MOCK-001"
    assert latest["request_id"] == "req-123"
    assert latest["outcome"] == "success"


def test_failed_privileged_action_records_failure(monkeypatch):
    monkeypatch.setattr("app.core.audit.audit_events_available", lambda: False)
    monkeypatch.setattr("app.core.audit.settings.persistence_backend", "json")

    log_audit_action(
        action="broker_configured",
        object_type="configuration",
        object_id="ibkr_readonly",
        actor_id="owner@example.com",
        outcome="failure",
        metadata={"reason": "invalid host"},
    )

    latest = next(entry for entry in get_audit_logs() if entry.get("action") == "broker_configured" and entry.get("outcome") == "failure")
    assert latest["outcome"] == "failure"


def test_sequential_audit_events_are_retained(monkeypatch):
    monkeypatch.setattr("app.core.audit.audit_events_available", lambda: False)
    monkeypatch.setattr("app.core.audit.settings.persistence_backend", "json")

    for index in range(25):
        log_audit_action(
            action="sequential_action",
            object_type="test",
            object_id=str(index),
            actor_id="worker",
            outcome="success",
        )

    logs = get_audit_logs()
    sequential = [entry for entry in logs if entry.get("action") == "sequential_action"]
    assert len(sequential) == 25


def test_audit_repo_has_no_update_api():
    from app.db import audit_event_repo

    assert not hasattr(audit_event_repo, "update_audit_event")
    assert not hasattr(audit_event_repo, "delete_audit_event")
