"""Portfolio-level Decision Packet — resolves capital/risk/tax conflicts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class PortfolioDecisionPacket(BaseModel):
    schema_version: str = "2.0.0"
    portfolio_decision_id: str
    account_scope: list[str]
    as_of: datetime
    holding_decision_ids: list[str] = Field(default_factory=list)
    urgent_decisions: list[str] = Field(default_factory=list)
    capital_budget: Decimal | float | None = None
    tax_budget: Decimal | float | None = None
    risk_budget_status: dict[str, Any] = Field(default_factory=dict)
    policy_breaches: list[str] = Field(default_factory=list)
    goal_feasibility: dict[str, Any] = Field(default_factory=dict)
    decision_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    construction_scenario_ids: list[str] = Field(default_factory=list)
    no_trade_scenario_id: str | None = None
    matrix_rows: list[dict[str, Any]] = Field(default_factory=list)
    packet_sha256: str = ""
    order_generated: bool = False
    requires_user_confirmation: bool = True
