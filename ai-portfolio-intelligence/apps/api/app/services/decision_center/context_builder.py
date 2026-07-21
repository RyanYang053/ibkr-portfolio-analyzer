"""Build complete DecisionContext from holding + market + plan evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.decision_context import DecisionContext
from app.services.decision_center.orchestrator import context_from_holding_dict


def build_decision_context(
    *,
    account_id: str,
    holding: dict[str, Any],
    as_of: datetime | None = None,
    policy: dict[str, Any] | None = None,
    financial_plan: dict[str, Any] | None = None,
    valuation_status: str | None = None,
    tax: dict[str, Any] | None = None,
    liquidity: dict[str, Any] | None = None,
) -> DecisionContext:
    """Assemble a DecisionContext with plan/policy and fail-closed valuation/tax/liquidity."""
    payload = dict(holding)
    if policy is not None:
        payload["policy"] = policy
    if financial_plan is not None:
        payload["financial_plan"] = financial_plan
    if valuation_status is not None:
        payload["valuation_status"] = valuation_status
    elif "valuation_status" not in payload:
        payload["valuation_status"] = "withheld"
    if tax is not None:
        payload["tax"] = tax
    elif "tax" not in payload and "tax_flags" in payload:
        payload["tax"] = payload["tax_flags"]
    if liquidity is not None:
        payload["liquidity"] = liquidity

    # Load plan/policy defaults when not supplied.
    if policy is None or financial_plan is None:
        try:
            from app.db.financial_plan_repo import FinancialPlanRepository

            plan = FinancialPlanRepository().latest()
            if plan is not None:
                if financial_plan is None:
                    payload["financial_plan"] = plan.model_dump(mode="json")
                if policy is None and plan.policy is not None:
                    payload["policy"] = plan.policy.model_dump(mode="json")
        except Exception:
            pass

    return context_from_holding_dict(
        account_id=account_id,
        holding=payload,
        as_of=as_of or datetime.now(timezone.utc),
    )
