"""Priority scoring for research candidates."""

from __future__ import annotations

from typing import Any

PRIORITY_ORDER = {"critical": 0, "high": 1, "routine": 2, "low": 3}


def score_research_priority(
    *,
    change_codes: list[str] | None = None,
    catalyst_days: int | None = None,
    decision_outcome: str | None = None,
    data_stale: bool = False,
) -> dict[str, Any]:
    codes = set(change_codes or [])
    score = 50
    if data_stale:
        score += 20
    if "thesis_invalidated" in codes or "hard_risk_breach" in codes:
        score += 40
    if "valuation_regime_change" in codes:
        score += 15
    if decision_outcome in {"review_exit", "review_trim", "data_insufficient"}:
        score += 25
    if catalyst_days is not None and catalyst_days <= 14:
        score += 10

    if score >= 90:
        label = "critical"
    elif score >= 70:
        label = "high"
    elif score >= 40:
        label = "routine"
    else:
        label = "low"

    return {"priority": label, "score": score, "reasons": sorted(codes)}


def sort_by_priority(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            PRIORITY_ORDER.get(str(item.get("priority", "routine")), 9),
            -float(item.get("score") or 0),
            str(item.get("symbol") or ""),
        ),
    )
