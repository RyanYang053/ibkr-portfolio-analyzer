from __future__ import annotations

from typing import Any

from app.services.decision_center.decision_validation import to_personal_decision_support
from app.services.decision_center.holding_context import HoldingContext

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
    """Ordered gates: data → thesis → risk/policy → valuation → portfolio fit → lens synthesis."""
    gates: list[dict[str, Any]] = []

    # 1. Data quality
    dq = context.data_quality
    if dq.get("status") != "ok" or dq.get("missing"):
        gates.append({"gate": "data_quality", "passed": False, "detail": dq})
        return _result("Data insufficient", gates, context)
    gates.append({"gate": "data_quality", "passed": True, "detail": dq})

    # 2. Thesis completeness
    thesis = context.thesis or {}
    thesis_ok = bool(thesis.get("text") or thesis.get("summary") or thesis.get("thesis_text"))
    gates.append({"gate": "thesis_completeness", "passed": thesis_ok, "detail": {"present": thesis_ok}})
    if not thesis_ok:
        return _result("Review thesis", gates, context)

    # 3. Risk / policy — require decimal units (e.g. -0.35), never infer percent.
    risk = context.risk or {}
    max_dd = risk.get("max_drawdown_decimal", risk.get("max_drawdown"))
    if max_dd is not None:
        max_dd_value = float(max_dd)
        if abs(max_dd_value) > 1.0:
            gates.append(
                {
                    "gate": "risk_policy",
                    "passed": False,
                    "detail": {
                        "max_drawdown": max_dd_value,
                        "error": "max_drawdown_must_be_decimal_unit",
                    },
                }
            )
            return _result("Data insufficient", gates, context)
        risk_flag = abs(max_dd_value) >= MAX_DRAWDOWN_DECIMAL_THRESHOLD
    else:
        risk_flag = False
    gates.append(
        {
            "gate": "risk_policy",
            "passed": not risk_flag,
            "detail": {"max_drawdown_decimal": max_dd},
        }
    )
    if risk_flag:
        return _result("Review trim", gates, context)

    # 4. Valuation — real gate; without approved valuation, never recommend add.
    valuation_ok = context.valuation_status in {"available", "approved"}
    gates.append(
        {
            "gate": "valuation_status",
            "passed": valuation_ok,
            "detail": {
                "valuation_status": context.valuation_status,
                "note": "Add reviews require available/approved valuation evidence.",
            },
        }
    )
    if not valuation_ok:
        return _result("Review thesis", gates, context)

    # 5. Portfolio fit
    fit = context.portfolio_fit or {}
    if fit.get("over_concentrated"):
        gates.append({"gate": "portfolio_fit", "passed": False, "detail": fit})
        return _result("Review trim", gates, context)
    gates.append({"gate": "portfolio_fit", "passed": True, "detail": fit})

    # 6. Lens synthesis
    ensemble = context.lens_ensemble or {}
    labels = list(ensemble.get("synthesis_labels") or [])
    gates.append({"gate": "lens_synthesis", "passed": True, "detail": {"labels": labels}})
    if "data_insufficient" in labels:
        return _result("Data insufficient", gates, context)
    if "inversion_flags" in labels or "risk_caution" in labels:
        return _result("Review trim", gates, context)
    if "quality_supportive" in labels and not fit.get("over_concentrated"):
        return _result("Review add", gates, context)

    return _result("No action", gates, context)


def _result(action: str, gates: list[dict[str, Any]], context: HoldingContext) -> dict[str, Any]:
    assert action in DECISION_ACTIONS
    personal = to_personal_decision_support(
        action=action,
        blockers=tuple(
            str(gate.get("gate"))
            for gate in gates
            if gate.get("passed") is False
        ),
        assumptions=("decision_center_holding_v0.1",),
    )
    assert personal.order_generated is False
    assert personal.requires_user_confirmation is True
    return {
        "instrument_key": context.instrument_key,
        "symbol": context.symbol,
        "action": action,
        "outcome": personal.outcome.value,
        "gates": gates,
        "valuation_status": context.valuation_status,
        "lens_ensemble": context.lens_ensemble,
        "methodology_id": "decision_center_holding",
        "methodology_status": "experimental",
        "order_generated": False,
        "requires_user_confirmation": True,
        "disclaimer": personal.disclaimer,
    }
