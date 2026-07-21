from __future__ import annotations

from typing import Any

from app.services.decision_center.holding_context import build_holding_context
from app.services.decision_center.holding_decision import evaluate_holding_decision
from app.services.decision_center.portfolio_orchestrator import build_portfolio_decision_packet


def build_portfolio_decision_matrix(
    *,
    account_id: str,
    holdings: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []
    weights: dict[str, float] = {}
    for item in holdings:
        symbol = str(item.get("symbol") or "")
        instrument_key = str(item.get("instrument_key") or symbol)
        context = build_holding_context(
            account_id=account_id,
            instrument_key=instrument_key,
            symbol=symbol,
            position=item.get("position") or item,
            fundamentals=item.get("fundamentals"),
            risk_metrics=item.get("risk_metrics"),
            factor_exposures=item.get("factor_exposures"),
            liquidity=item.get("liquidity"),
            tax_flags=item.get("tax_flags"),
            thesis=item.get("thesis"),
            valuation_status=str(item.get("valuation_status") or "withheld"),
        )
        decision = evaluate_holding_decision(context)
        packets.append(decision)
        weight = float(
            (item.get("position") or item).get("portfolio_weight")
            or (item.get("position") or item).get("weight")
            or 0
        )
        if symbol:
            weights[symbol] = weights.get(symbol, 0.0) + weight
        rows.append(
            {
                "instrument_key": instrument_key,
                "symbol": symbol,
                "action": decision["action"],
                "outcome": decision.get("outcome"),
                "decision_id": decision.get("decision_id"),
                "priority": decision.get("priority"),
                "confidence_status": decision.get("confidence_status"),
                "blockers": decision.get("blockers") or [],
                "gates": decision["gates"],
                "lens_ensemble": context.lens_ensemble,
                "valuation_status": context.valuation_status,
                "order_generated": False,
            }
        )
    portfolio_packet = build_portfolio_decision_packet(
        account_id=account_id,
        holding_packets=packets,
        current_weights=weights,
    )
    return {
        "account_id": account_id,
        "holdings": rows,
        "portfolio_decision": portfolio_packet.model_dump(mode="json"),
        "methodology_id": "decision_center_holding",
        "methodology_status": "experimental",
        "valuation_disclosure": "Valuation remains withheld pending methodology approval for personal use.",
        "order_generated": False,
    }
