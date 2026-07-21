"""No-trade baseline always present and order_generated False."""

from __future__ import annotations

from app.services.portfolio_construction.no_trade_baseline import build_no_trade_baseline
from app.services.portfolio_construction.scenario_service import build_construction_scenarios


def test_no_trade_baseline_has_zero_turnover() -> None:
    baseline = build_no_trade_baseline(current_weights={"AAPL": 10.0, "MSFT": 8.0}, account_id="acct")
    assert baseline["scenario_type"] == "no_trade"
    assert baseline["turnover"] == 0.0
    assert baseline["order_generated"] is False
    assert baseline["orders"] == []


def test_construction_scenarios_always_include_no_trade() -> None:
    result = build_construction_scenarios(
        account_id="acct",
        current_weights={"AAPL": 10.0},
        target_weights={"AAPL": 8.0, "CASH": 2.0},
    )
    types = [s["scenario_type"] for s in result["scenarios"]]
    assert "no_trade" in types
    for required in (
        "policy_repair",
        "minimum_turnover",
        "maximum_risk_reduction",
        "tax_aware",
        "goal_aligned",
        "cash_deployment",
    ):
        assert required in types
    assert result["order_generated"] is False
    assert all(s.get("order_generated") is False for s in result["scenarios"])
    assert all(s.get("orders") == [] for s in result["scenarios"])
    assert result.get("no_trade_scenario_id")
