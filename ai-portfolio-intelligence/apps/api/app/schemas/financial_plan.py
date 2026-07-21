"""Financial plan, goals, and investment policy schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class FinancialGoal(BaseModel):
    goal_id: str
    name: str
    goal_type: str = "general"  # retirement | education | home | emergency | general
    target_amount: float
    currency: str = "USD"
    target_date: date | None = None
    priority: int = 1
    funded_amount: float = 0.0
    monthly_contribution: float | None = None
    status: str = "active"
    notes: str | None = None


class AccountRole(BaseModel):
    account_id: str
    role: str  # growth | income | tax_advantaged | taxable | emergency | speculative
    tax_wrapper: str | None = None  # taxable | ira | 401k | hsa | trust | other
    contribution_priority: int = 1
    notes: str | None = None


class ContributionPlan(BaseModel):
    plan_id: str
    account_id: str
    amount: float
    frequency: Literal["weekly", "biweekly", "monthly", "quarterly", "annual"] = "monthly"
    start_date: date | None = None
    end_date: date | None = None
    goal_id: str | None = None
    auto_invest_hint: bool = False
    notes: str | None = None


class InvestmentPolicy(BaseModel):
    policy_id: str
    version: str = "1.0.0"
    risk_tolerance: str = "moderate"  # conservative | moderate | aggressive
    max_single_position_pct: float = 10.0
    max_sector_pct: float = 35.0
    max_speculative_pct: float = 5.0
    min_cash_pct: float = 2.0
    target_equity_pct: float | None = None
    target_fixed_income_pct: float | None = None
    rebalance_band_pct: float = 5.0
    tax_loss_harvesting: bool = False
    prohibited_symbols: list[str] = Field(default_factory=list)
    preferred_asset_classes: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class GoalFeasibility(BaseModel):
    goal_id: str
    feasible: bool
    projected_funded_amount: float
    shortfall: float
    required_monthly_contribution: float | None = None
    assumptions: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)


class FinancialPlan(BaseModel):
    schema_version: str = "1.0.0"
    plan_id: str
    owner_label: str = "personal"
    base_currency: str = "USD"
    planning_horizon_years: int = 10
    goals: list[FinancialGoal] = Field(default_factory=list)
    account_roles: list[AccountRole] = Field(default_factory=list)
    contribution_plans: list[ContributionPlan] = Field(default_factory=list)
    policy: InvestmentPolicy | None = None
    feasibility: list[GoalFeasibility] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    notes: str | None = None


class FinancialPlanUpsert(BaseModel):
    owner_label: str = "personal"
    base_currency: str = "USD"
    planning_horizon_years: int = 10
    goals: list[FinancialGoal] = Field(default_factory=list)
    account_roles: list[AccountRole] = Field(default_factory=list)
    contribution_plans: list[ContributionPlan] = Field(default_factory=list)
    policy: InvestmentPolicy | None = None
    notes: str | None = None
