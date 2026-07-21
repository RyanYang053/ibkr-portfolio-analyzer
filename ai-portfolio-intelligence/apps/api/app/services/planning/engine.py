"""Planning engine — assemble and persist financial plans."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.financial_plan_repo import FinancialPlanRepository
from app.schemas.financial_plan import FinancialPlan, FinancialPlanUpsert
from app.services.planning.account_roles import merge_account_roles
from app.services.planning.contribution_plan import build_default_contributions
from app.services.planning.goal_feasibility import assess_goal_feasibility
from app.services.planning.policy_builder import build_policy


class PlanningEngine:
    def __init__(self, repo: FinancialPlanRepository | None = None) -> None:
        self.repo = repo or FinancialPlanRepository()

    def get_plan(self, plan_id: str = "default") -> FinancialPlan | None:
        return self.repo.get(plan_id)

    def upsert_plan(
        self,
        payload: FinancialPlanUpsert,
        *,
        plan_id: str = "default",
        account_ids: list[str] | None = None,
    ) -> FinancialPlan:
        now = datetime.now(timezone.utc)
        existing = self.repo.get(plan_id)
        policy = payload.policy or build_policy(
            risk_tolerance=(payload.policy.risk_tolerance if payload.policy else "moderate"),
            goals=payload.goals,
            existing=existing.policy if existing else None,
        )
        account_roles = merge_account_roles(
            payload.account_roles or (existing.account_roles if existing else []),
            account_ids or [],
        )
        contributions = list(payload.contribution_plans)
        if not contributions and payload.goals:
            default_account = account_roles[0].account_id if account_roles else "primary"
            contributions = build_default_contributions(payload.goals, default_account_id=default_account)

        feasibility = [
            assess_goal_feasibility(goal, contributions) for goal in payload.goals
        ]
        plan = FinancialPlan(
            plan_id=plan_id or f"plan_{uuid4().hex[:12]}",
            owner_label=payload.owner_label,
            base_currency=payload.base_currency,
            planning_horizon_years=payload.planning_horizon_years,
            goals=payload.goals,
            account_roles=account_roles,
            contribution_plans=contributions,
            policy=policy,
            feasibility=feasibility,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            notes=payload.notes,
        )
        return self.repo.save(plan)

    def rebuild_policy(self, plan_id: str = "default", *, risk_tolerance: str = "moderate") -> FinancialPlan:
        plan = self.repo.get(plan_id)
        if plan is None:
            raise ValueError("plan_not_found")
        plan.policy = build_policy(
            risk_tolerance=risk_tolerance,
            goals=plan.goals,
            existing=plan.policy,
        )
        plan.updated_at = datetime.now(timezone.utc)
        return self.repo.save(plan)
