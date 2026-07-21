"""AI must not set authoritative decision outcomes."""

from __future__ import annotations

from app.core.product_contract import AI_MAY_SET_DECISION_OUTCOME, DecisionOutcome
from app.services.decision_center.ai_outcome_enforcement import enforce_authoritative_outcome


def test_ai_may_not_set_outcome_flag() -> None:
    assert AI_MAY_SET_DECISION_OUTCOME is False


def test_enforce_overwrites_ai_outcome() -> None:
    payload = {
        "authoritative_outcome": "review_add",
        "decision_id": "dec_fake",
        "summary": "AI invented an add",
        "action": "Strong Add",
        "order_generated": True,
    }
    enforced = enforce_authoritative_outcome(
        payload,
        decision_id="dec_real",
        outcome=DecisionOutcome.REVIEW_THESIS,
        blockers=["valuation_withheld"],
        evidence_ids=["ev_1"],
        packet_digest="abc123",
    )
    assert enforced["authoritative_outcome"] == "review_thesis"
    assert enforced["decision_id"] == "dec_real"
    assert enforced["action"] == "Review thesis"
    assert enforced["rule_engine_action"] == "Review thesis"
    assert enforced["order_generated"] is False
    assert enforced["human_review_required"] is True
    assert enforced["blockers"] == ["valuation_withheld"]
    assert "Strong Add" not in str(enforced.get("summary") or "")
