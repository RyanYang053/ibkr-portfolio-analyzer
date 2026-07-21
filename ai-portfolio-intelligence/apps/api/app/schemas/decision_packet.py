"""Holding Decision Packet schema — authoritative user-facing outcome."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.product_contract import (
    ORDER_GENERATED_DEFAULT,
    DecisionOutcome,
    ImplementationStatus,
)
from app.schemas.decision_gate import GateResult
from app.schemas.decision_scenario import DecisionScenario
from app.schemas.evidence import EvidenceRef


class HoldingDecisionPacket(BaseModel):
    schema_version: str = "2.0.0"
    decision_id: str
    account_id: str
    instrument_key: str
    symbol: str
    as_of: datetime
    evidence_cutoff: datetime
    outcome: DecisionOutcome
    candidate_outcome: DecisionOutcome
    previous_outcome: DecisionOutcome | None = None
    outcome_changed: bool = False
    change_reason_codes: list[str] = Field(default_factory=list)
    priority: str = "routine"
    confidence_status: str = "provisional"
    implementation_status: ImplementationStatus = ImplementationStatus.BLOCKED
    gates: list[GateResult] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    scenarios: list[DecisionScenario] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    changes: list[dict[str, Any]] = Field(default_factory=list)
    review_triggers: list[dict[str, Any]] = Field(default_factory=list)
    next_review_date: date | None = None
    calculation_run_ids: list[str] = Field(default_factory=list)
    methodology_versions: dict[str, str] = Field(default_factory=dict)
    packet_sha256: str = ""
    requires_user_confirmation: bool = True
    order_generated: bool = False
    # Compatibility fields for existing UI
    action: str | None = None
    valuation_status: str = "withheld"
    lens_ensemble: dict[str, Any] = Field(default_factory=dict)
    methodology_id: str = "decision_center_holding"
    methodology_status: str = "experimental"
    disclaimer: str | None = None

    @model_validator(mode="after")
    def _enforce_invariants(self) -> HoldingDecisionPacket:
        if self.order_generated or self.order_generated is not ORDER_GENERATED_DEFAULT and self.order_generated:
            raise ValueError("order_generated must remain False")
        object.__setattr__(self, "order_generated", False)
        if not self.requires_user_confirmation:
            raise ValueError("requires_user_confirmation must remain True")
        if not any(s.scenario_type == "no_trade" for s in self.scenarios):
            # Allow empty during construction; orchestrator always injects no_trade.
            pass
        return self


class DecisionUserResponse(BaseModel):
    decision_id: str
    response: str  # accepted_for_review | rejected | deferred | modified | no_action | acted_outside_app
    intended_weight: float | None = None
    reasoning: str | None = None
    responded_at: datetime | None = None
