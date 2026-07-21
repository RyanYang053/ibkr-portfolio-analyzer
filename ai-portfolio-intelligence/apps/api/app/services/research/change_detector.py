"""Detect material changes between decision packets / snapshots."""

from __future__ import annotations

from typing import Any


def detect_changes(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    if not previous:
        return [{"change_code": "initial_observation", "severity": "info"}]

    changes: list[dict[str, Any]] = []
    prev_outcome = previous.get("outcome")
    curr_outcome = current.get("outcome")
    if prev_outcome and curr_outcome and prev_outcome != curr_outcome:
        changes.append(
            {
                "change_code": "outcome_changed",
                "severity": "high",
                "from": prev_outcome,
                "to": curr_outcome,
            }
        )

    prev_weight = float(previous.get("portfolio_weight") or previous.get("weight") or 0)
    curr_weight = float(current.get("portfolio_weight") or current.get("weight") or 0)
    if abs(curr_weight - prev_weight) >= 2.0:
        changes.append(
            {
                "change_code": "weight_drift",
                "severity": "medium",
                "from": prev_weight,
                "to": curr_weight,
            }
        )

    if previous.get("thesis_status") != current.get("thesis_status") and current.get("thesis_status"):
        changes.append(
            {
                "change_code": "thesis_status_changed",
                "severity": "high",
                "from": previous.get("thesis_status"),
                "to": current.get("thesis_status"),
            }
        )

    if current.get("hard_risk_breach") and not previous.get("hard_risk_breach"):
        changes.append({"change_code": "hard_risk_breach", "severity": "critical"})

    if not changes:
        changes.append({"change_code": "no_material_change", "severity": "info"})
    return changes
