"""Trade Plan domain contract (plan §9).

A Trade Plan is a first-class, auditable *intention* to act — never an order.
"Approved" means "approved for manual consideration", not transmitted to a broker.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TradePlanStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED_FOR_MANUAL_CONSIDERATION = "approved_for_manual_consideration"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    IMPORTED_EXECUTION_MATCHED = "imported_execution_matched"
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"


class TradeDirection(str, Enum):
    BUY = "buy"
    ADD = "add"
    TRIM = "trim"
    EXIT = "exit"
    SHORT = "short"


class SizingMethod(str, Enum):
    MAX_LOSS = "max_loss"
    VOLATILITY = "volatility"
    ATR = "atr"
    RISK_CONTRIBUTION = "risk_contribution"
    FIXED_PERCENT = "fixed_percent"
    SCENARIO_LOSS = "scenario_loss"
    USER_ENTERED = "user_entered"


class SizingResult(BaseModel):
    method: SizingMethod
    proposed_quantity: float
    proposed_notional: float
    maximum_loss: float
    position_weight_after_pct: Optional[float] = None
    sector_weight_after_pct: Optional[float] = None
    cash_after: Optional[float] = None
    invalidating_assumptions: list[str] = Field(default_factory=list)
    inputs: dict[str, object] = Field(default_factory=dict)


class TradePlanCheck(BaseModel):
    check_id: str
    passed: bool
    detail: str = ""
    waived: bool = False


class TradePlanChecklist(BaseModel):
    checks: list[TradePlanCheck]
    ready: bool
    blocking: list[str] = Field(default_factory=list)


class TradePlan(BaseModel):
    trade_plan_id: str
    account_id: str
    instrument_id: str
    symbol: str
    direction: TradeDirection
    plan_type: str = "discretionary"
    status: TradePlanStatus = TradePlanStatus.DRAFT

    thesis_version_id: Optional[str] = None
    decision_packet_id: Optional[str] = None

    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    invalidation_price: Optional[float] = None
    target_low: Optional[float] = None
    target_high: Optional[float] = None

    maximum_loss: Optional[float] = None
    risk_budget_pct: Optional[float] = None
    sizing_method: Optional[SizingMethod] = None
    proposed_quantity: Optional[float] = None
    proposed_notional: Optional[float] = None
    current_position: float = 0.0
    resulting_position: Optional[float] = None
    holding_period: Optional[str] = None

    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tax_estimate: Optional[dict[str, object]] = None
    liquidity_status: str = "unknown"
    portfolio_fit_status: str = "unknown"
    data_readiness: str = "unknown"

    checklist: Optional[TradePlanChecklist] = None
    user_acknowledged_limitations: bool = False

    # A Trade Plan can never place an order — this is asserted, not configurable.
    order_generated: bool = False

    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class TradePlanCreate(BaseModel):
    account_id: str
    instrument_id: str
    symbol: Optional[str] = None
    direction: TradeDirection
    plan_type: str = "discretionary"
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    invalidation_price: Optional[float] = None
    target_low: Optional[float] = None
    target_high: Optional[float] = None
    risk_budget_pct: Optional[float] = None
    sizing_method: Optional[SizingMethod] = None
    proposed_quantity: Optional[float] = None
    holding_period: Optional[str] = None
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    thesis_version_id: Optional[str] = None
    decision_packet_id: Optional[str] = None


class TradePlanUpdate(BaseModel):
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    invalidation_price: Optional[float] = None
    target_low: Optional[float] = None
    target_high: Optional[float] = None
    risk_budget_pct: Optional[float] = None
    sizing_method: Optional[SizingMethod] = None
    proposed_quantity: Optional[float] = None
    holding_period: Optional[str] = None
    catalysts: Optional[list[str]] = None
    risks: Optional[list[str]] = None
    user_acknowledged_limitations: Optional[bool] = None
