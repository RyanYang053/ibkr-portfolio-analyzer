from __future__ import annotations

from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult
from app.services.decision_center.gates.base import gate_result


class SuitabilityGate:
    gate_id = "suitability"
    order = 3

    def evaluate(self, context: DecisionContext) -> GateResult:
        policy = context.policy or {}
        restrictions = list(policy.get("restricted_securities") or [])
        symbol = (context.symbol or "").upper()
        if symbol and symbol in {str(s).upper() for s in restrictions}:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="high",
                blockers=["restricted_security"],
                details={"symbol": symbol},
            )
        return gate_result(self.gate_id, passed=True)


class ThesisGate:
    gate_id = "thesis"
    order = 4

    def evaluate(self, context: DecisionContext) -> GateResult:
        if context.thesis_status == "invalidated":
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="critical",
                blockers=["thesis_invalidated"],
                details={"thesis_status": context.thesis_status},
            )
        thesis = context.thesis or {}
        thesis_ok = bool(thesis.get("text") or thesis.get("summary") or thesis.get("thesis_text"))
        if not thesis_ok:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=False,
                severity="high",
                blockers=["thesis_incomplete"],
                details={"present": False},
            )
        return gate_result(self.gate_id, passed=True, details={"present": True})


class RiskPolicyGate:
    gate_id = "risk_policy"
    order = 5

    def evaluate(self, context: DecisionContext) -> GateResult:
        if context.hard_risk_breach or context.hard_policy_breach:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="critical",
                blockers=["hard_risk_or_policy_breach"],
                details={
                    "hard_risk_breach": context.hard_risk_breach,
                    "hard_policy_breach": context.hard_policy_breach,
                },
            )
        risk = context.risk or {}
        plan = context.financial_plan or {}
        max_dd = risk.get("max_drawdown_decimal", risk.get("max_drawdown"))
        threshold = float(plan.get("maximum_acceptable_drawdown", 0.35))
        if max_dd is not None:
            max_dd_value = float(max_dd)
            if abs(max_dd_value) > 1.0:
                return gate_result(
                    self.gate_id,
                    passed=False,
                    terminal=True,
                    severity="critical",
                    blockers=["max_drawdown_must_be_decimal_unit"],
                    details={"max_drawdown": max_dd_value},
                )
            if abs(max_dd_value) >= threshold:
                return gate_result(
                    self.gate_id,
                    passed=False,
                    terminal=True,
                    severity="high",
                    blockers=["drawdown_breach"],
                    details={"max_drawdown_decimal": max_dd_value, "threshold": threshold},
                )
        return gate_result(self.gate_id, passed=True, details={"max_drawdown_decimal": max_dd})
