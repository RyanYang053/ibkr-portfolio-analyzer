"""No-trade baseline scenario for portfolio construction."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.core.product_contract import ORDER_GENERATED_DEFAULT


def build_no_trade_baseline(
    *,
    current_weights: dict[str, float],
    account_id: str | None = None,
) -> dict[str, Any]:
    """Always-present baseline: keep current weights, zero turnover, no orders."""
    return {
        "scenario_id": f"no_trade_{uuid4().hex[:10]}",
        "scenario_type": "no_trade",
        "account_id": account_id,
        "proposed_weights": dict(current_weights),
        "turnover": 0.0,
        "expected_tax": 0.0,
        "expected_transaction_cost": 0.0,
        "implementation_ready": True,
        "blockers": [],
        "compared_to_no_trade": {"delta": 0},
        "order_generated": ORDER_GENERATED_DEFAULT,
        "orders": [],
    }


def assert_no_orders(scenario: dict[str, Any]) -> dict[str, Any]:
    scenario = dict(scenario)
    scenario["order_generated"] = False
    scenario["orders"] = []
    return scenario
