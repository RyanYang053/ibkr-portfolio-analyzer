"""Holding decision evaluation — delegates to DecisionOrchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.decision_center.decision_validation import to_personal_decision_support
from app.services.decision_center.holding_context import HoldingContext
from app.services.decision_center.orchestrator import DecisionOrchestrator, context_from_holding_dict

DECISION_ACTIONS = (
    "No action",
    "Review add",
    "Review trim",
    "Review exit",
    "Review thesis",
    "Data insufficient",
)

MAX_DRAWDOWN_DECIMAL_THRESHOLD = 0.35


def evaluate_holding_decision(context: HoldingContext) -> dict[str, Any]:
    """Ordered gates via orchestrator; returns dict compatible with existing routes/UI."""
    holding = {
        "instrument_key": context.instrument_key,
        "symbol": context.symbol,
        "data_quality": context.data_quality,
        "thesis": context.thesis,
        "risk": context.risk,
        "risk_metrics": context.risk,
        "valuation_status": context.valuation_status,
        "portfolio_fit": context.portfolio_fit,
        "lens_ensemble": context.lens_ensemble,
        "position": {
            "portfolio_weight": (context.portfolio_fit or {}).get("weight"),
            "weight": (context.portfolio_fit or {}).get("weight"),
        },
        "fundamentals": {"present": True} if (context.data_quality or {}).get("status") == "ok" else {},
        "tax": dict(context.tax_flags or {}),
        "liquidity": dict(context.liquidity or {"status": "incomplete"}),
    }
    # Preserve prior concentration semantics when fit already set.
    decision_context = context_from_holding_dict(
        account_id=context.account_id,
        holding=holding,
        as_of=datetime.now(timezone.utc),
    )
    packet = DecisionOrchestrator().evaluate(decision_context)
    personal = to_personal_decision_support(
        action=packet.action or "Data insufficient",
        blockers=tuple(packet.blockers),
        assumptions=("decision_center_holding_v0.2",),
    )
    assert personal.order_generated is False
    assert personal.requires_user_confirmation is True
    result = packet.model_dump(mode="json")
    # Ensure legacy keys remain stable for tests/UI.
    result["action"] = packet.action
    result["outcome"] = packet.outcome.value
    result["order_generated"] = False
    result["requires_user_confirmation"] = True
    result["disclaimer"] = personal.disclaimer
    # Legacy gate shape used gate/detail; GateResult uses gate_id/details.
    normalized_gates: list[dict[str, Any]] = []
    for gate in result.get("gates") or []:
        if not isinstance(gate, dict):
            continue
        normalized_gates.append(
            {
                **gate,
                "gate": gate.get("gate") or gate.get("gate_id"),
                "detail": gate.get("detail") if "detail" in gate else gate.get("details") or {},
            }
        )
    result["gates"] = normalized_gates
    return result
