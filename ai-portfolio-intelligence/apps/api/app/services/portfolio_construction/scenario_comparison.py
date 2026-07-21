"""Compare construction scenarios against the no-trade baseline."""

from __future__ import annotations

from typing import Any


def compare_scenarios(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    no_trade = next((s for s in scenarios if s.get("scenario_type") == "no_trade"), None)
    ranked: list[dict[str, Any]] = []
    for scenario in scenarios:
        if scenario.get("scenario_type") == "no_trade":
            continue
        ranked.append(
            {
                "scenario_id": scenario.get("scenario_id"),
                "scenario_type": scenario.get("scenario_type"),
                "turnover": scenario.get("turnover"),
                "implementation_ready": scenario.get("implementation_ready"),
                "blockers": scenario.get("blockers") or [],
                "vs_no_trade": scenario.get("compared_to_no_trade") or {},
            }
        )
    ranked.sort(key=lambda row: (not row.get("implementation_ready"), float(row.get("turnover") or 0)))
    return {
        "no_trade_scenario_id": (no_trade or {}).get("scenario_id"),
        "ranked": ranked,
        "preferred": ranked[0] if ranked else None,
        "order_generated": False,
    }
