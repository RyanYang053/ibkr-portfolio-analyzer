from __future__ import annotations

from typing import Any

from app.services.decision_center.holding_context import build_holding_context
from app.services.decision_center.holding_decision import evaluate_holding_decision


def build_portfolio_decision_matrix(
    *,
    account_id: str,
    holdings: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
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
        )
        decision = evaluate_holding_decision(context)
        rows.append(
            {
                "instrument_key": instrument_key,
                "symbol": symbol,
                "action": decision["action"],
                "gates": decision["gates"],
                "lens_ensemble": context.lens_ensemble,
                "valuation_status": context.valuation_status,
            }
        )
    return {
        "account_id": account_id,
        "holdings": rows,
        "methodology_id": "decision_center_holding",
        "methodology_status": "experimental",
        "valuation_disclosure": "Valuation remains withheld pending methodology approval.",
    }
