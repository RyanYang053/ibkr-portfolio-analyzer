"""Decision hysteresis — stabilize soft changes; allow hard breaches immediately."""

from __future__ import annotations

from app.core.product_contract import DecisionOutcome

HARD_OUTCOMES = {
    DecisionOutcome.DATA_INSUFFICIENT,
    DecisionOutcome.REVIEW_EXIT,
    DecisionOutcome.REVIEW_TRIM,
}


def stabilize_outcome(
    *,
    candidate: DecisionOutcome,
    previous: DecisionOutcome | None,
    material_change: bool = False,
    hard_breach: bool = False,
    confirmation_count: int = 0,
    required_confirmations: int = 2,
) -> DecisionOutcome:
    """Return stabilized outcome.

    Hard data/policy/thesis breaches apply immediately.
    Non-material soft transitions require repeated confirmation.
    Material soft transitions apply immediately (still recorded as candidate vs stabilized).
    """
    if previous is None or candidate == previous:
        return candidate
    if hard_breach or candidate in HARD_OUTCOMES:
        return candidate
    if material_change:
        return candidate
    if confirmation_count >= required_confirmations:
        return candidate
    return previous
