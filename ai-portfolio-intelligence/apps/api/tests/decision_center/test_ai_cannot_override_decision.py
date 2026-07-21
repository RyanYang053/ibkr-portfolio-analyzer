"""AI cannot override authoritative decision outcomes."""

from __future__ import annotations

from app.core.product_contract import AI_MAY_SET_DECISION_OUTCOME, ORDER_GENERATED_DEFAULT, DecisionOutcome
from app.services.decision_center.ai_outcome_enforcement import enforce_authoritative_outcome


def test_flag_remains_false() -> None:
    assert AI_MAY_SET_DECISION_OUTCOME is False
    assert ORDER_GENERATED_DEFAULT is False


def test_ai_payload_cannot_set_outcome_or_orders() -> None:
    payload = {
        "authoritative_outcome": "review_add",
        "order_generated": True,
        "summary": "AI wants add",
    }
    enforced = enforce_authoritative_outcome(
        payload,
        decision_id="dec_1",
        outcome=DecisionOutcome.MONITOR,
        blockers=["human_review_required"],
    )
    assert enforced["authoritative_outcome"] == "monitor"
    assert enforced["order_generated"] is False
    assert enforced["human_review_required"] is True
    assert enforced["decision_id"] == "dec_1"
