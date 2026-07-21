"""Decision calibration tracking — state store + optional SQL table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.state_store import get_state_store

_NAMESPACE = "decision_calibration"


def record_calibration_observation(
    *,
    decision_id: str,
    outcome: str,
    user_response: str | None,
    realized_label: str | None = None,
) -> dict[str, Any]:
    row = {
        "decision_id": decision_id,
        "outcome": outcome,
        "user_response": user_response,
        "realized_label": realized_label,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "methodology_status": "experimental",
    }
    store = get_state_store()
    store.write_json(_NAMESPACE, decision_id, row)
    index = store.read_json(_NAMESPACE, "index", default={"ids": []}) or {}
    ids = list(index.get("ids") or [])
    if decision_id not in ids:
        ids.insert(0, decision_id)
    store.write_json(_NAMESPACE, "index", {"ids": ids[:1000]})
    if settings.persistence_backend in {"postgres", "sqlite"}:
        try:
            _save_sql(row)
        except Exception:
            pass
    return row


def _save_sql(row: dict[str, Any]) -> None:
    from sqlalchemy import text

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        # Table from 0035_decision_calibration — insert if present.
        session.execute(
            text(
                """
                INSERT INTO decision_calibration_observations (
                    decision_id, outcome, user_response, realized_label, recorded_at
                ) VALUES (
                    :decision_id, :outcome, :user_response, :realized_label, :recorded_at
                )
                """
            ),
            {
                "decision_id": row["decision_id"],
                "outcome": row["outcome"],
                "user_response": row.get("user_response"),
                "realized_label": row.get("realized_label"),
                "recorded_at": row.get("recorded_at"),
            },
        )
        session.commit()


def calibration_summary() -> dict[str, Any]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, "index", default={"ids": []}) or {}
    counts: dict[str, int] = {}
    with_response = 0
    with_realized = 0
    for decision_id in list(index.get("ids") or []):
        row = store.read_json(_NAMESPACE, str(decision_id), default=None) or {}
        outcome = str(row.get("outcome") or "unknown")
        counts[outcome] = counts.get(outcome, 0) + 1
        if row.get("user_response"):
            with_response += 1
        if row.get("realized_label"):
            with_realized += 1
    return {
        "outcome_counts": counts,
        "observations": len(index.get("ids") or []),
        "with_user_response": with_response,
        "with_realized_label": with_realized,
        "status": "provisional",
        "methodology_status": "experimental",
        "confidence_status": "withheld",
        "order_generated": False,
    }
