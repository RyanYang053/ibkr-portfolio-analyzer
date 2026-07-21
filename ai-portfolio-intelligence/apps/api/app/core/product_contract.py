"""Frozen product contracts for the Personal Investment Decision Operating System."""

from __future__ import annotations

from enum import StrEnum

# Permanent invariants — never flip these in production code paths.
ORDER_SUBMISSION_ALLOWED = False
AI_MAY_SET_DECISION_OUTCOME = False
MISSING_CRITICAL_DATA_FAILS_CLOSED = True
NO_TRADE_SCENARIO_REQUIRED = True
LOCAL_SINGLE_OWNER = True
HUMAN_REVIEW_REQUIRED = True
ORDER_GENERATED_DEFAULT = False

AUTHORITATIVE_OUTCOME_SOURCE = "decision_center"

# Score / optimizer labels that must never appear as authoritative user outcomes.
FORBIDDEN_AUTHORITATIVE_ACTIONS: frozenset[str] = frozenset(
    {
        "Strong Add",
        "Add",
        "Buy",
        "Sell",
        "Trim Review",
        "Exit Review",
        "Avoid",
        "Hold",
        "Watch",
    }
)


class DecisionOutcome(StrEnum):
    DATA_INSUFFICIENT = "data_insufficient"
    MONITOR = "monitor"
    REVIEW_THESIS = "review_thesis"
    REVIEW_ADD = "review_add"
    REVIEW_TRIM = "review_trim"
    REVIEW_EXIT = "review_exit"


class ImplementationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"
    REVIEW_READY = "review_ready"


class MethodologyStatus(StrEnum):
    WITHHELD = "withheld"
    EXPERIMENTAL = "experimental"
    INTERNALLY_VALIDATED = "internally_validated"
    APPROVED_FOR_PERSONAL_USE = "approved_for_personal_use"
    RETIRED = "retired"


class EvidenceQuality(StrEnum):
    AVAILABLE = "available"
    PROVISIONAL = "provisional"
    EXPERIMENTAL = "experimental"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    WITHHELD = "withheld"
    FAILED = "failed"


class ConfidenceStatus(StrEnum):
    WITHHELD = "withheld"
    LOW_EVIDENCE = "low_evidence"
    PROVISIONAL = "provisional"
    INTERNALLY_VALIDATED = "internally_validated"
    APPROVED = "approved"


class ScoreInterpretation(StrEnum):
    """Analytical score labels — evidence only, never authoritative outcomes."""

    HIGH_HEURISTIC_SCORE = "high_heuristic_score"
    SUPPORTIVE_SCORE = "supportive_score"
    MIXED_SCORE = "mixed_score"
    WEAK_SCORE = "weak_score"
    HIGH_RISK_SCORE = "high_risk_score"
    DATA_INSUFFICIENT = "data_insufficient"


DECISION_OUTCOME_VALUES: frozenset[str] = frozenset(o.value for o in DecisionOutcome)

ACTION_LABEL_TO_OUTCOME: dict[str, DecisionOutcome] = {
    "No action": DecisionOutcome.MONITOR,
    "Monitor": DecisionOutcome.MONITOR,
    "Review add": DecisionOutcome.REVIEW_ADD,
    "Review trim": DecisionOutcome.REVIEW_TRIM,
    "Review exit": DecisionOutcome.REVIEW_EXIT,
    "Review thesis": DecisionOutcome.REVIEW_THESIS,
    "Data insufficient": DecisionOutcome.DATA_INSUFFICIENT,
}

OUTCOME_TO_ACTION_LABEL: dict[DecisionOutcome, str] = {
    DecisionOutcome.MONITOR: "No action",
    DecisionOutcome.REVIEW_ADD: "Review add",
    DecisionOutcome.REVIEW_TRIM: "Review trim",
    DecisionOutcome.REVIEW_EXIT: "Review exit",
    DecisionOutcome.REVIEW_THESIS: "Review thesis",
    DecisionOutcome.DATA_INSUFFICIENT: "Data insufficient",
}
