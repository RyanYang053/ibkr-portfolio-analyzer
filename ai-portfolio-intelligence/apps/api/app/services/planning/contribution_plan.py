"""Contribution plan helpers."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.schemas.financial_plan import ContributionPlan, FinancialGoal


def build_default_contributions(
    goals: list[FinancialGoal],
    *,
    default_account_id: str,
) -> list[ContributionPlan]:
    plans: list[ContributionPlan] = []
    for goal in goals:
        amount = float(goal.monthly_contribution or 0.0)
        if amount <= 0 and goal.target_amount > goal.funded_amount:
            # Spread remaining over 60 months as a starting hint
            amount = round((float(goal.target_amount) - float(goal.funded_amount)) / 60.0, 2)
        if amount <= 0:
            continue
        plans.append(
            ContributionPlan(
                plan_id=f"contrib_{uuid4().hex[:10]}",
                account_id=default_account_id,
                amount=amount,
                frequency="monthly",
                start_date=date.today(),
                goal_id=goal.goal_id,
                auto_invest_hint=False,
                notes="Suggested contribution — informational only",
            )
        )
    return plans


def annualize_contribution(plan: ContributionPlan) -> float:
    amount = float(plan.amount)
    if plan.frequency == "weekly":
        return amount * 52.0
    if plan.frequency == "biweekly":
        return amount * 26.0
    if plan.frequency == "monthly":
        return amount * 12.0
    if plan.frequency == "quarterly":
        return amount * 4.0
    return amount
