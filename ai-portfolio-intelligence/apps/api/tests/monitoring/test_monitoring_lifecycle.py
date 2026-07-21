"""Monitoring event lifecycle: acknowledge, snooze, resolve."""

from __future__ import annotations

from app.services.decision_center.monitoring_service import (
    acknowledge_monitoring_event,
    persist_monitoring_event,
    resolve_monitoring_event,
    snooze_monitoring_event,
)


def test_monitoring_event_lifecycle(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")

    event = persist_monitoring_event(
        {
            "account_id": "ACC1",
            "instrument_key": "AAPL:1",
            "rule_type": "concentration",
            "message": "test",
            "status": "open",
        }
    )
    event_id = event["event_id"]
    ack = acknowledge_monitoring_event(event_id, note="seen")
    assert ack is not None
    assert ack["status"] == "acknowledged"
    snoozed = snooze_monitoring_event(event_id, snooze_until="2099-01-01T00:00:00+00:00")
    assert snoozed is not None
    assert snoozed["status"] == "snoozed"
    resolved = resolve_monitoring_event(event_id)
    assert resolved is not None
    assert resolved["status"] == "resolved"
