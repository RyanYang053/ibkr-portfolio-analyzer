"""Track decision outcome changes and forward observation windows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.state_store import get_state_store

_NAMESPACE = "decision_outcome_history"
_OBSERVATIONS = "decision_outcome_observations"
_WINDOWS_DAYS = (30, 90, 180, 365)


def record_outcome_transition(
    *,
    account_id: str,
    instrument_key: str,
    decision_id: str,
    previous_outcome: str | None,
    outcome: str,
    change_reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    event = {
        "account_id": account_id,
        "instrument_key": instrument_key,
        "decision_id": decision_id,
        "previous_outcome": previous_outcome,
        "outcome": outcome,
        "change_reason_codes": list(change_reason_codes or []),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    store = get_state_store()
    key = f"{decision_id}:{event['recorded_at']}"
    store.write_json(_NAMESPACE, key, event)
    index_key = f"index:{account_id}:{instrument_key}"
    index = store.read_json(_NAMESPACE, index_key, default={"keys": []}) or {}
    keys = list(index.get("keys") or [])
    keys.insert(0, key)
    store.write_json(_NAMESPACE, index_key, {"keys": keys[:200]})
    # Seed observation windows for later calibration (returns filled when market data exists).
    schedule_outcome_observations(
        account_id=account_id,
        instrument_key=instrument_key,
        decision_id=decision_id,
        outcome=outcome,
        as_of=event["recorded_at"],
    )
    return event


def schedule_outcome_observations(
    *,
    account_id: str,
    instrument_key: str,
    decision_id: str,
    outcome: str,
    as_of: str,
) -> list[dict[str, Any]]:
    store = get_state_store()
    try:
        start = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        start = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for days in _WINDOWS_DAYS:
        due = start + timedelta(days=days)
        row = {
            "observation_id": f"{decision_id}:{days}d",
            "account_id": account_id,
            "instrument_key": instrument_key,
            "decision_id": decision_id,
            "outcome": outcome,
            "window_days": days,
            "as_of": start.isoformat(),
            "due_at": due.isoformat(),
            "status": "scheduled",
            "realized_return": None,
            "max_drawdown": None,
            "no_trade_baseline_return": None,
            "notes": "Filled when walk-forward observation job runs; withheld until calibrated.",
        }
        store.write_json(_OBSERVATIONS, row["observation_id"], row)
        rows.append(row)
    index_key = f"index:{account_id}:{instrument_key}"
    index = store.read_json(_OBSERVATIONS, index_key, default={"ids": []}) or {}
    ids = list(index.get("ids") or [])
    for row in rows:
        if row["observation_id"] not in ids:
            ids.insert(0, row["observation_id"])
    store.write_json(_OBSERVATIONS, index_key, {"ids": ids[:200]})
    return rows


def list_outcome_history(account_id: str, instrument_key: str, limit: int = 50) -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{account_id}:{instrument_key}", default={"keys": []}) or {}
    out: list[dict[str, Any]] = []
    for key in list(index.get("keys") or [])[:limit]:
        row = store.read_json(_NAMESPACE, str(key), default=None)
        if row:
            out.append(row)
    return out


def list_outcome_observations(
    account_id: str,
    instrument_key: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_OBSERVATIONS, f"index:{account_id}:{instrument_key}", default={"ids": []}) or {}
    out: list[dict[str, Any]] = []
    for obs_id in list(index.get("ids") or [])[:limit]:
        row = store.read_json(_OBSERVATIONS, str(obs_id), default=None)
        if row:
            out.append(row)
    return out
