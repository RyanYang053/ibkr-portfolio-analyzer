from __future__ import annotations

from typing import Any


def simulate_holding_action(
    *,
    action: str,
    current_weight: float,
    proposed_weight: float | None = None,
    estimated_tax: float | None = None,
) -> dict[str, Any]:
    """Deterministic action simulator — review framing only, no order language."""
    target = proposed_weight if proposed_weight is not None else current_weight
    delta = target - current_weight
    if action.lower() in {"trim", "exit", "review trim", "review exit"}:
        direction = "reduce"
    elif action.lower() in {"add", "review add"}:
        direction = "increase"
    else:
        direction = "hold"
    return {
        "action": action,
        "direction": direction,
        "current_weight_percent": current_weight,
        "proposed_weight_percent": target,
        "weight_delta_percent": round(delta, 4),
        "estimated_tax": estimated_tax,
        "implementation_ready": False,
        "note": "Simulation is decision-support only; not an order or recommendation to trade.",
        "methodology_status": "experimental",
    }
