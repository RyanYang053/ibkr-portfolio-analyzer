"""Policy builder tests."""

from __future__ import annotations

from datetime import date, timedelta

from app.schemas.financial_plan import FinancialGoal
from app.services.planning.policy_builder import build_policy


def test_moderate_policy_defaults() -> None:
    policy = build_policy(risk_tolerance="moderate")
    assert policy.risk_tolerance == "moderate"
    assert policy.max_single_position_pct == 10.0
    assert policy.policy_id.startswith("pol_")


def test_short_horizon_tightens_speculative_cap() -> None:
    goal = FinancialGoal(
        goal_id="g1",
        name="Near term",
        target_amount=10000,
        target_date=date.today() + timedelta(days=365),
    )
    policy = build_policy(risk_tolerance="aggressive", goals=[goal])
    assert policy.constraints.get("short_horizon") is True
    assert policy.max_speculative_pct <= 2.0
