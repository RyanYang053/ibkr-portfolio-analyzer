"""Build no-trade and change scenarios for a holding decision."""

from __future__ import annotations

from uuid import uuid4

from app.core.product_contract import DecisionOutcome, ImplementationStatus
from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult
from app.schemas.decision_scenario import DecisionScenario


def build_decision_scenarios(
    context: DecisionContext,
    outcome: DecisionOutcome,
    gate_results: list[GateResult],
) -> list[DecisionScenario]:
    weight = float(
        context.position.get("portfolio_weight")
        or context.position.get("weight")
        or 0
    )
    impl_blockers = []
    for gate in gate_results:
        if gate.gate_id in {"tax", "liquidity", "implementation"} and not gate.passed:
            impl_blockers.extend(gate.blockers)

    tax_status = (context.tax or {}).get("methodology_status") or (context.tax or {}).get("status")
    tax_ready = tax_status not in {None, "unknown", "withheld", "withheld_lot_inputs_unavailable", "failed"}
    implementation_status = (
        ImplementationStatus.REVIEW_READY
        if not impl_blockers and tax_ready
        else ImplementationStatus.BLOCKED
    )

    no_trade = DecisionScenario(
        scenario_id=f"scn_{uuid4().hex[:12]}",
        scenario_type="no_trade",
        proposed_weight_percent=weight,
        expected_tax=0,
        expected_transaction_cost=0,
        expected_exit_days=0,
        cash_impact=0,
        risk_change={},
        implementation_status=ImplementationStatus.NOT_APPLICABLE,
        implementation_ready=True,
        blockers=[],
        compared_to_no_trade={"delta": 0},
    )

    scenarios = [no_trade]
    proposed = {
        DecisionOutcome.REVIEW_ADD: ("increase", min(weight + 2.0, 100.0)),
        DecisionOutcome.REVIEW_TRIM: ("reduce", max(weight * 0.5, 0.0)),
        DecisionOutcome.REVIEW_EXIT: ("exit", 0.0),
        DecisionOutcome.REVIEW_THESIS: ("no_trade", weight),
        DecisionOutcome.MONITOR: ("no_trade", weight),
        DecisionOutcome.DATA_INSUFFICIENT: ("no_trade", weight),
    }
    scenario_type, proposed_weight = proposed[outcome]
    if scenario_type != "no_trade":
        scenarios.append(
            DecisionScenario(
                scenario_id=f"scn_{uuid4().hex[:12]}",
                scenario_type=scenario_type,
                proposed_weight_percent=proposed_weight,
                expected_tax=None if not tax_ready else 0,
                expected_transaction_cost=None,
                expected_exit_days=None,
                cash_impact=None,
                risk_change={"weight_delta": proposed_weight - weight},
                implementation_status=implementation_status,
                implementation_ready=implementation_status == ImplementationStatus.REVIEW_READY,
                blockers=list(impl_blockers),
                compared_to_no_trade={
                    "weight_delta": proposed_weight - weight,
                    "no_trade_scenario_id": no_trade.scenario_id,
                },
            )
        )
    return scenarios
