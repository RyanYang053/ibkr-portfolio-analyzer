"""Personal decision-support outcomes (signals, never orders)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.product_contract import (
    ACTION_LABEL_TO_OUTCOME,
    DecisionOutcome,
    HUMAN_REVIEW_REQUIRED,
    ORDER_GENERATED_DEFAULT,
)
from app.core.product_scope import DECISION_DISCLAIMER

# Re-export for existing imports.
__all__ = [
    "DecisionOutcome",
    "DecisionEvidence",
    "PersonalDecisionSupport",
    "ACTION_TO_OUTCOME",
    "to_personal_decision_support",
]

ACTION_TO_OUTCOME = ACTION_LABEL_TO_OUTCOME


@dataclass(frozen=True)
class DecisionEvidence:
    key: str
    detail: str


@dataclass(frozen=True)
class PersonalDecisionSupport:
    outcome: DecisionOutcome
    evidence: tuple[DecisionEvidence, ...]
    assumptions: tuple[str, ...]
    blockers: tuple[str, ...]
    scenario_only: bool
    requires_user_confirmation: bool = True
    order_generated: bool = False
    disclaimer: str = DECISION_DISCLAIMER

    def __post_init__(self) -> None:
        if self.order_generated:
            raise ValueError("Personal decision support must never generate orders")
        if not self.requires_user_confirmation:
            raise ValueError("Personal decision support always requires user confirmation")


def to_personal_decision_support(
    *,
    action: str,
    evidence: tuple[DecisionEvidence, ...] = (),
    assumptions: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
    scenario_only: bool = False,
) -> PersonalDecisionSupport:
    outcome = ACTION_TO_OUTCOME.get(action, DecisionOutcome.DATA_INSUFFICIENT)
    return PersonalDecisionSupport(
        outcome=outcome,
        evidence=evidence,
        assumptions=assumptions,
        blockers=blockers,
        scenario_only=scenario_only,
        requires_user_confirmation=HUMAN_REVIEW_REQUIRED,
        order_generated=ORDER_GENERATED_DEFAULT,
    )
