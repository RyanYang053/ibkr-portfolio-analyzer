"""Personal decision-support outcomes (signals, never orders)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.product_scope import DECISION_DISCLAIMER


class DecisionOutcome(StrEnum):
    MONITOR = "monitor"
    REVIEW_ADD = "review_add"
    REVIEW_REDUCE = "review_reduce"
    REVIEW_EXIT = "review_exit"
    THESIS_STRENGTHENING = "thesis_strengthening"
    THESIS_WEAKENING = "thesis_weakening"
    WITHHELD = "withheld"


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


ACTION_TO_OUTCOME: dict[str, DecisionOutcome] = {
    "No action": DecisionOutcome.MONITOR,
    "Review add": DecisionOutcome.REVIEW_ADD,
    "Review trim": DecisionOutcome.REVIEW_REDUCE,
    "Review exit": DecisionOutcome.REVIEW_EXIT,
    "Review thesis": DecisionOutcome.THESIS_WEAKENING,
    "Data insufficient": DecisionOutcome.WITHHELD,
}


def to_personal_decision_support(
    *,
    action: str,
    evidence: tuple[DecisionEvidence, ...] = (),
    assumptions: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
    scenario_only: bool = False,
) -> PersonalDecisionSupport:
    outcome = ACTION_TO_OUTCOME.get(action, DecisionOutcome.WITHHELD)
    return PersonalDecisionSupport(
        outcome=outcome,
        evidence=evidence,
        assumptions=assumptions,
        blockers=blockers,
        scenario_only=scenario_only,
        requires_user_confirmation=True,
        order_generated=False,
    )
