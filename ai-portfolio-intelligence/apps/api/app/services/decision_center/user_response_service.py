"""Persist user responses to Decision Packets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.state_store import get_state_store
from app.schemas.decision_packet import DecisionUserResponse

_NAMESPACE = "decision_user_responses"


def record_user_response(response: DecisionUserResponse) -> dict[str, Any]:
    payload = response.model_dump(mode="json")
    if payload.get("responded_at") is None:
        payload["responded_at"] = datetime.now(timezone.utc).isoformat()
    store = get_state_store()
    key = f"{response.decision_id}:{payload['responded_at']}"
    store.write_json(_NAMESPACE, key, payload)
    index = store.read_json(_NAMESPACE, f"index:{response.decision_id}", default={"keys": []}) or {}
    keys = list(index.get("keys") or [])
    keys.insert(0, key)
    store.write_json(_NAMESPACE, f"index:{response.decision_id}", {"keys": keys[:100]})
    return payload


def list_responses(decision_id: str) -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{decision_id}", default={"keys": []}) or {}
    out: list[dict[str, Any]] = []
    for key in list(index.get("keys") or []):
        row = store.read_json(_NAMESPACE, str(key), default=None)
        if row:
            out.append(row)
    return out
