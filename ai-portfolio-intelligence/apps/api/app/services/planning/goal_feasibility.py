"""Goal feasibility heuristics."""

from __future__ import annotations

from datetime import date

from app.schemas.financial_plan import ContributionPlan, FinancialGoal, GoalFeasibility


def _months_until(target: date | None, *, today: date | None = None) -> int | None:
    if target is None:
        return None
    as_of = today or date.today()
    months = (target.year - as_of.year) * 12 + (target.month - as_of.month)
    return max(months, 0)


def assess_goal_feasibility(
    goal: FinancialGoal,
    contributions: list[ContributionPlan],
    *,
    assumed_annual_return: float = 0.05,
    today: date | None = None,
) -> GoalFeasibility:
    """Simple contribution + return projection; not a certified planner output."""
    months = _months_until(goal.target_date, today=today)
    related = [c for c in contributions if c.goal_id == goal.goal_id or c.goal_id is None]
    monthly = float(goal.monthly_contribution or 0.0)
    for plan in related:
        if plan.frequency == "monthly":
            monthly += float(plan.amount)
        elif plan.frequency == "biweekly":
            monthly += float(plan.amount) * 26.0 / 12.0
        elif plan.frequency == "weekly":
            monthly += float(plan.amount) * 52.0 / 12.0
        elif plan.frequency == "quarterly":
            monthly += float(plan.amount) / 3.0
        elif plan.frequency == "annual":
            monthly += float(plan.amount) / 12.0

    blockers: list[str] = []
    if months is None:
        blockers.append("missing_target_date")
        horizon_months = 120
    else:
        horizon_months = months if months > 0 else 1

    monthly_rate = assumed_annual_return / 12.0
    balance = float(goal.funded_amount)
    for _ in range(horizon_months):
        balance = balance * (1.0 + monthly_rate) + monthly

    shortfall = max(float(goal.target_amount) - balance, 0.0)
    required: float | None = None
    if shortfall > 0 and horizon_months > 0:
        # Annuity FV solve approximation for required monthly add
        if monthly_rate > 0:
            factor = ((1.0 + monthly_rate) ** horizon_months - 1.0) / monthly_rate
            growth = float(goal.funded_amount) * ((1.0 + monthly_rate) ** horizon_months)
            required = max((float(goal.target_amount) - growth) / factor, 0.0)
        else:
            required = max((float(goal.target_amount) - float(goal.funded_amount)) / horizon_months, 0.0)

    feasible = shortfall <= 0 and "missing_target_date" not in blockers
    return GoalFeasibility(
        goal_id=goal.goal_id,
        feasible=feasible,
        projected_funded_amount=round(balance, 2),
        shortfall=round(shortfall, 2),
        required_monthly_contribution=round(required, 2) if required is not None else None,
        assumptions={
            "assumed_annual_return": assumed_annual_return,
            "horizon_months": horizon_months,
            "monthly_contribution_used": round(monthly, 2),
        },
        blockers=blockers,
    )
