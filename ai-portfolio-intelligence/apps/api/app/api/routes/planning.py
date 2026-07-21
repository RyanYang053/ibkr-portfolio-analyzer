"""Financial plan / goals / policy API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import Principal, get_current_principal
from app.schemas.financial_plan import (
    AccountRole,
    FinancialGoal,
    FinancialPlan,
    FinancialPlanUpsert,
)
from app.services.planning.engine import PlanningEngine

router = APIRouter(
    prefix="/planning",
    tags=["planning"],
    dependencies=[Depends(get_current_principal)],
)


class RebuildPolicyRequest(BaseModel):
    risk_tolerance: str = Field(default="moderate")


class AccountRolesUpsert(BaseModel):
    account_roles: list[AccountRole] = Field(default_factory=list)


@router.get("/plan", response_model=FinancialPlan | dict[str, Any])
def get_plan(plan_id: str = "default") -> FinancialPlan | dict[str, Any]:
    plan = PlanningEngine().get_plan(plan_id)
    if plan is None:
        return {
            "plan_id": plan_id,
            "exists": False,
            "message": "No financial plan yet. Create one via PUT /planning/plan.",
            "order_generated": False,
        }
    return plan


@router.put("/plan", response_model=FinancialPlan)
def upsert_plan(
    payload: FinancialPlanUpsert,
    plan_id: str = "default",
    principal: Principal = Depends(get_current_principal),
) -> FinancialPlan:
    _ = principal
    return PlanningEngine().upsert_plan(payload, plan_id=plan_id)


@router.post("/plan/rebuild-policy", response_model=FinancialPlan)
def rebuild_policy(body: RebuildPolicyRequest, plan_id: str = "default") -> FinancialPlan:
    try:
        return PlanningEngine().rebuild_policy(plan_id, risk_tolerance=body.risk_tolerance)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/goals")
def list_goals(plan_id: str = "default") -> dict[str, Any]:
    plan = PlanningEngine().get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return {
        "plan_id": plan.plan_id,
        "goals": [g.model_dump(mode="json") for g in plan.goals],
        "order_generated": False,
    }


@router.post("/goals")
def create_goal(goal: FinancialGoal, plan_id: str = "default") -> dict[str, Any]:
    engine = PlanningEngine()
    plan = engine.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    goals = [g for g in plan.goals if g.goal_id != goal.goal_id]
    goals.append(goal)
    updated = engine.upsert_plan(
        FinancialPlanUpsert(
            owner_label=plan.owner_label,
            base_currency=plan.base_currency,
            planning_horizon_years=plan.planning_horizon_years,
            goals=goals,
            account_roles=plan.account_roles,
            contribution_plans=plan.contribution_plans,
            policy=plan.policy,
            notes=plan.notes,
        ),
        plan_id=plan_id,
    )
    return {
        "plan_id": updated.plan_id,
        "goal": goal.model_dump(mode="json"),
        "feasibility": [f.model_dump(mode="json") for f in updated.feasibility],
        "order_generated": False,
    }


@router.put("/goals/{goal_id}")
def update_goal(goal_id: str, goal: FinancialGoal, plan_id: str = "default") -> dict[str, Any]:
    if goal.goal_id != goal_id:
        raise HTTPException(status_code=400, detail="goal_id_mismatch")
    return create_goal(goal, plan_id=plan_id)


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: str, plan_id: str = "default") -> dict[str, Any]:
    engine = PlanningEngine()
    plan = engine.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    goals = [g for g in plan.goals if g.goal_id != goal_id]
    if len(goals) == len(plan.goals):
        raise HTTPException(status_code=404, detail="goal_not_found")
    updated = engine.upsert_plan(
        FinancialPlanUpsert(
            owner_label=plan.owner_label,
            base_currency=plan.base_currency,
            planning_horizon_years=plan.planning_horizon_years,
            goals=goals,
            account_roles=plan.account_roles,
            contribution_plans=plan.contribution_plans,
            policy=plan.policy,
            notes=plan.notes,
        ),
        plan_id=plan_id,
    )
    return {"plan_id": updated.plan_id, "deleted_goal_id": goal_id, "order_generated": False}


@router.get("/account-roles")
def list_account_roles(plan_id: str = "default") -> dict[str, Any]:
    plan = PlanningEngine().get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return {
        "plan_id": plan.plan_id,
        "account_roles": [r.model_dump(mode="json") for r in plan.account_roles],
        "order_generated": False,
    }


@router.put("/account-roles")
def upsert_account_roles(body: AccountRolesUpsert, plan_id: str = "default") -> dict[str, Any]:
    engine = PlanningEngine()
    plan = engine.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    updated = engine.upsert_plan(
        FinancialPlanUpsert(
            owner_label=plan.owner_label,
            base_currency=plan.base_currency,
            planning_horizon_years=plan.planning_horizon_years,
            goals=plan.goals,
            account_roles=body.account_roles,
            contribution_plans=plan.contribution_plans,
            policy=plan.policy,
            notes=plan.notes,
        ),
        plan_id=plan_id,
        account_ids=[r.account_id for r in body.account_roles],
    )
    return {
        "plan_id": updated.plan_id,
        "account_roles": [r.model_dump(mode="json") for r in updated.account_roles],
        "order_generated": False,
    }


@router.get("/feasibility")
def feasibility(plan_id: str = "default") -> dict[str, Any]:
    plan = PlanningEngine().get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="plan_not_found")
    return {
        "plan_id": plan.plan_id,
        "feasibility": [f.model_dump(mode="json") for f in plan.feasibility],
        "order_generated": False,
    }
