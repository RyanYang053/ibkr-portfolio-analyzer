"""Monitoring event persistence."""

from __future__ import annotations

from app.services.decision_center.monitoring_service import list_monitoring_events, persist_monitoring_event


def test_persist_and_list_monitoring_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")

    from app.db import state_store

    monkeypatch.setattr(state_store.settings, "persistence_backend", "json")
    # Force state root under tmp if supported
    event = persist_monitoring_event(
        {
            "account_id": "acct-test",
            "instrument_key": "AAPL",
            "rule_type": "concentration",
            "severity": "medium",
            "message": "weight breach",
        }
    )
    assert event["event_id"]
    listed = list_monitoring_events("acct-test")
    assert any(e.get("event_id") == event["event_id"] for e in listed)
