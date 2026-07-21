"""Onboarding state-machine contract (plan §21).

Onboarding status is persisted in SQLite — NOT browser localStorage — so setup
survives reinstalls and is a durable workflow, not a disposable checklist.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# The 20 setup stages (§21), in order.
ONBOARDING_STAGES: tuple[str, ...] = (
    "welcome",
    "local_storage",
    "currency_locale",
    "tax_residency",
    "account_discovery",
    "account_role_mapping",
    "ibkr_connection",
    "flex_configuration",
    "historical_import",
    "reconciliation",
    "investor_profile",
    "financial_goals",
    "investment_policy",
    "alert_preferences",
    "backup_creation",
    "restore_verification",
    "data_health_validation",
    "first_portfolio_snapshot",
    "first_decision_packet",
    "setup_summary",
)

# Stage groupings for readiness scoring (§21).
READINESS_GROUPS: dict[str, tuple[str, ...]] = {
    "portfolio_data": ("account_discovery", "ibkr_connection", "historical_import", "first_portfolio_snapshot"),
    "tax_data": ("tax_residency", "reconciliation"),
    "research": ("investor_profile", "first_decision_packet"),
    "decision": ("financial_goals", "investment_policy", "first_decision_packet"),
    "backup": ("backup_creation", "restore_verification"),
}


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class OnboardingStage(BaseModel):
    stage: str
    status: StageStatus = StageStatus.NOT_STARTED
    detected_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    validation_status: str = "unknown"
    blockers: list[str] = Field(default_factory=list)
    user_acknowledged: bool = False


class OnboardingStageUpdate(BaseModel):
    status: StageStatus
    validation_status: Optional[str] = None
    blockers: Optional[list[str]] = None
    user_acknowledged: Optional[bool] = None
