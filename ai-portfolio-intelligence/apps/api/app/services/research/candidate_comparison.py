"""Side-by-side candidate comparison."""

from __future__ import annotations

from typing import Any


def compare_candidates(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    fields = ("priority", "score", "outcome", "symbol", "source")
    diffs = []
    for field in fields:
        if left.get(field) != right.get(field):
            diffs.append(
                {
                    "field": field,
                    "left": left.get(field),
                    "right": right.get(field),
                }
            )
    return {
        "left_candidate_id": left.get("candidate_id"),
        "right_candidate_id": right.get("candidate_id"),
        "differences": diffs,
        "prefer": (
            left.get("candidate_id")
            if float(left.get("score") or 0) >= float(right.get("score") or 0)
            else right.get("candidate_id")
        ),
        "order_generated": False,
    }
