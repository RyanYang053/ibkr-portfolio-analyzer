"""Monitoring evaluation and event persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.db.state_store import get_state_store
from app.services.decision_center.monitoring_rules import evaluate_monitoring_rules, list_monitoring_rules
from app.services.notifications.dispatcher import dispatch_decision_alert

_EVENTS = "monitoring_events"


def persist_monitoring_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    payload.setdefault("event_id", f"mevt_{uuid4().hex[:12]}")
    payload.setdefault("detected_at", datetime.now(timezone.utc).isoformat())
    store = get_state_store()
    store.write_json(_EVENTS, payload["event_id"], payload)
    account_id = str(payload.get("account_id") or "default")
    index = store.read_json(_EVENTS, f"index:{account_id}", default={"ids": []}) or {}
    ids = list(index.get("ids") or [])
    ids.insert(0, payload["event_id"])
    store.write_json(_EVENTS, f"index:{account_id}", {"ids": ids[:500]})
    return payload


def list_monitoring_events(account_id: str, limit: int = 100) -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_EVENTS, f"index:{account_id}", default={"ids": []}) or {}
    out: list[dict[str, Any]] = []
    for event_id in list(index.get("ids") or [])[:limit]:
        row = store.read_json(_EVENTS, str(event_id), default=None)
        if row:
            out.append(row)
    return out


def update_monitoring_event(
    event_id: str,
    *,
    status: str,
    note: str | None = None,
    snooze_until: str | None = None,
) -> dict[str, Any] | None:
    store = get_state_store()
    row = store.read_json(_EVENTS, event_id, default=None)
    if not isinstance(row, dict):
        return None
    updated = dict(row)
    updated["status"] = status
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    if note:
        updated["status_note"] = note
    if snooze_until:
        updated["snooze_until"] = snooze_until
    if status == "acknowledged":
        updated["acknowledged_at"] = updated["updated_at"]
    if status == "resolved":
        updated["resolved_at"] = updated["updated_at"]
    store.write_json(_EVENTS, event_id, updated)
    return updated


def acknowledge_monitoring_event(event_id: str, note: str | None = None) -> dict[str, Any] | None:
    return update_monitoring_event(event_id, status="acknowledged", note=note)


def resolve_monitoring_event(event_id: str, note: str | None = None) -> dict[str, Any] | None:
    return update_monitoring_event(event_id, status="resolved", note=note)


def snooze_monitoring_event(
    event_id: str,
    *,
    snooze_until: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    return update_monitoring_event(
        event_id,
        status="snoozed",
        note=note,
        snooze_until=snooze_until,
    )


def run_monitoring_evaluation(
    *,
    account_id: str,
    holdings: list[dict[str, Any]],
    risk_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = list_monitoring_rules(account_id)
    evaluation = evaluate_monitoring_rules(
        account_id,
        holdings=holdings,
        risk_metrics=risk_metrics,
    )
    events: list[dict[str, Any]] = []
    for item in list(evaluation.get("alerts") or []):
        message = f"Monitoring rule triggered: {item.get('rule_type')}"
        event = persist_monitoring_event(
            {
                "account_id": account_id,
                "instrument_key": item.get("instrument_key"),
                "rule_id": item.get("rule_id"),
                "rule_type": item.get("rule_type"),
                "severity": "medium",
                "message": message,
                "payload": item,
                "status": "open",
            }
        )
        events.append(event)
        dispatch_decision_alert(
            account_id=account_id,
            title=f"Monitoring: {event.get('instrument_key') or 'portfolio'}",
            body=message,
            severity="medium",
        )
    return {
        "account_id": account_id,
        "rules_evaluated": len(rules),
        "events": events,
        "evaluation": evaluation,
        "order_generated": False,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
