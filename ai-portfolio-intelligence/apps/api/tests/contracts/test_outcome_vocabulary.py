"""Outcome vocabulary contract tests."""

from __future__ import annotations

from app.core.product_contract import (
    ACTION_LABEL_TO_OUTCOME,
    DECISION_OUTCOME_VALUES,
    DecisionOutcome,
    ImplementationStatus,
    MethodologyStatus,
)
from app.services.decision_center.decision_validation import to_personal_decision_support


def test_canonical_outcomes() -> None:
    assert DECISION_OUTCOME_VALUES == {
        "data_insufficient",
        "monitor",
        "review_thesis",
        "review_add",
        "review_trim",
        "review_exit",
    }
    assert "withheld" not in DECISION_OUTCOME_VALUES
    assert "review_reduce" not in DECISION_OUTCOME_VALUES


def test_action_mapping() -> None:
    assert ACTION_LABEL_TO_OUTCOME["Review trim"] == DecisionOutcome.REVIEW_TRIM
    assert ACTION_LABEL_TO_OUTCOME["Data insufficient"] == DecisionOutcome.DATA_INSUFFICIENT
    assert ACTION_LABEL_TO_OUTCOME["Review thesis"] == DecisionOutcome.REVIEW_THESIS


def test_personal_support_uses_canonical_outcomes() -> None:
    personal = to_personal_decision_support(action="Review trim")
    assert personal.outcome == DecisionOutcome.REVIEW_TRIM
    assert personal.order_generated is False


def test_implementation_and_methodology_statuses() -> None:
    assert ImplementationStatus.BLOCKED.value == "blocked"
    assert MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value == "approved_for_personal_use"
