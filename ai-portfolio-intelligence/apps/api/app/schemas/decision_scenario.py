"""Decision scenario schema."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.product_contract import ImplementationStatus


class DecisionScenario(BaseModel):
    scenario_id: str
    scenario_type: str
    proposed_weight_percent: float | None = None
    proposed_quantity: float | None = None
    funding_source: str | None = None
    expected_tax: Decimal | float | None = None
    expected_transaction_cost: Decimal | float | None = None
    expected_exit_days: float | None = None
    cash_impact: Decimal | float | None = None
    risk_change: dict[str, float | None] = Field(default_factory=dict)
    policy_changes: dict[str, Any] = Field(default_factory=dict)
    goal_impact: dict[str, Any] = Field(default_factory=dict)
    selected_tax_lots: list[dict[str, Any]] = Field(default_factory=list)
    implementation_status: ImplementationStatus | str = ImplementationStatus.BLOCKED
    implementation_ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    compared_to_no_trade: dict[str, Any] = Field(default_factory=dict)
