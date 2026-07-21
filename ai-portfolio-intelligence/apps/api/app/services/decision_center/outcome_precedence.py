"""Deterministic outcome precedence from gate results."""

from __future__ import annotations

from app.core.product_contract import OUTCOME_TO_ACTION_LABEL, DecisionOutcome
from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult


def resolve_outcome(
    gates: list[GateResult],
    context: DecisionContext,
) -> DecisionOutcome:
    failed = {gate.gate_id: gate for gate in gates if not gate.passed}

    if "source_integrity" in failed or "data_quality" in failed:
        return DecisionOutcome.DATA_INSUFFICIENT

    if context.thesis_status == "invalidated":
        return DecisionOutcome.REVIEW_EXIT

    if context.hard_risk_breach or context.hard_policy_breach:
        return DecisionOutcome.REVIEW_TRIM

    if "risk_policy" in failed:
        return DecisionOutcome.REVIEW_TRIM

    if "portfolio_fit" in failed:
        return DecisionOutcome.REVIEW_TRIM

    if "thesis" in failed:
        return DecisionOutcome.REVIEW_THESIS

    if "valuation" in failed:
        return DecisionOutcome.REVIEW_THESIS

    valuation_approved = context.valuation_status in {"approved", "approved_for_personal_use"}
    labels = list((context.lens_ensemble or {}).get("synthesis_labels") or [])
    if "data_insufficient" in labels:
        return DecisionOutcome.DATA_INSUFFICIENT
    if "inversion_flags" in labels or "risk_caution" in labels:
        return DecisionOutcome.REVIEW_TRIM

    supportive = context.supportive_quality_evidence or "quality_supportive" in labels
    if supportive and valuation_approved and context.add_capacity_available:
        # Tax/liquidity failures block implementation_ready, not the review_add outcome.
        return DecisionOutcome.REVIEW_ADD

    if supportive and not valuation_approved:
        return DecisionOutcome.REVIEW_THESIS

    return DecisionOutcome.MONITOR


def outcome_to_action(outcome: DecisionOutcome) -> str:
    return OUTCOME_TO_ACTION_LABEL[outcome]
