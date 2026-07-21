"""Backend enforcement: AI payloads never override Decision Packet outcomes."""

from __future__ import annotations

from typing import Any

from app.core.product_contract import (
    AI_MAY_SET_DECISION_OUTCOME,
    FORBIDDEN_AUTHORITATIVE_ACTIONS,
    OUTCOME_TO_ACTION_LABEL,
    DecisionOutcome,
    HUMAN_REVIEW_REQUIRED,
    ORDER_GENERATED_DEFAULT,
)


def enforce_authoritative_outcome(
    payload: dict[str, Any],
    *,
    decision_id: str,
    outcome: DecisionOutcome,
    blockers: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    opposing_evidence_ids: list[str] | None = None,
    packet_digest: str | None = None,
    packet_version: str = "2.0.0",
) -> dict[str, Any]:
    """Overwrite any AI-supplied outcome fields with the deterministic packet."""
    if AI_MAY_SET_DECISION_OUTCOME:
        raise RuntimeError("AI_MAY_SET_DECISION_OUTCOME must remain False")

    result = dict(payload)
    label = OUTCOME_TO_ACTION_LABEL.get(outcome, "Data insufficient")
    result["decision_id"] = decision_id
    result["decision_packet_version"] = packet_version
    result["authoritative_outcome"] = outcome.value
    result["outcome"] = outcome.value
    # Never leave competing score/AI action labels as the user-facing action.
    result["action"] = label
    result["rule_engine_action"] = label
    result["score_interpretation"] = result.get("score_interpretation") or result.get("action_evidence")
    # Strip forbidden authoritative phrasing from free-text fields if present.
    for key in ("summary", "title", "recommendation_summary", "headline"):
        value = result.get(key)
        if isinstance(value, str):
            for banned in FORBIDDEN_AUTHORITATIVE_ACTIONS:
                if banned.lower() in value.lower():
                    result[key] = (
                        f"Decision Center outcome: {label}. "
                        "Score/AI language was demoted to evidence only."
                    )
                    break
    result["blockers"] = list(blockers or result.get("blockers") or [])
    result["supporting_evidence_ids"] = list(evidence_ids or result.get("supporting_evidence_ids") or [])
    result["opposing_evidence_ids"] = list(
        opposing_evidence_ids or result.get("opposing_evidence_ids") or []
    )
    result["human_review_required"] = HUMAN_REVIEW_REQUIRED
    result["order_generated"] = ORDER_GENERATED_DEFAULT
    if packet_digest is not None:
        result["packet_digest"] = packet_digest
    result["questions_for_user"] = list(result.get("questions_for_user") or [])
    return result
