"""Policy repair suggestions — informational only."""

from __future__ import annotations

from typing import Any

from app.schemas.financial_plan import InvestmentPolicy


def suggest_policy_repairs(
    *,
    policy: InvestmentPolicy | None,
    current_weights: dict[str, float],
    sector_weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    if policy is None:
        repairs.append(
            {
                "code": "missing_policy",
                "severity": "high",
                "message": "No investment policy on file. Create one in Planning.",
            }
        )
        return repairs

    for symbol, weight in current_weights.items():
        if weight > float(policy.max_single_position_pct):
            repairs.append(
                {
                    "code": "single_position_breach",
                    "severity": "medium",
                    "symbol": symbol,
                    "weight": weight,
                    "limit": policy.max_single_position_pct,
                    "message": f"{symbol} exceeds max single-position policy.",
                    "suggested_action": "review_trim",
                }
            )

    for sector, weight in (sector_weights or {}).items():
        if weight > float(policy.max_sector_pct):
            repairs.append(
                {
                    "code": "sector_breach",
                    "severity": "medium",
                    "sector": sector,
                    "weight": weight,
                    "limit": policy.max_sector_pct,
                    "message": f"{sector} exceeds max sector policy.",
                    "suggested_action": "review_trim",
                }
            )

    cash = float(current_weights.get("CASH", 0.0) or current_weights.get("__cash__", 0.0) or 0.0)
    if cash < float(policy.min_cash_pct):
        repairs.append(
            {
                "code": "cash_below_minimum",
                "severity": "low",
                "cash_pct": cash,
                "limit": policy.min_cash_pct,
                "message": "Cash below policy minimum.",
                "suggested_action": "review_add_cash",
            }
        )

    return repairs
