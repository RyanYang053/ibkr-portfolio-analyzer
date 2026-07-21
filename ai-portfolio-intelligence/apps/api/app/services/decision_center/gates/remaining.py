from __future__ import annotations

from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult
from app.services.decision_center.gates.base import gate_result


class FundamentalQualityGate:
    gate_id = "fundamental_quality"
    order = 6

    def evaluate(self, context: DecisionContext) -> GateResult:
        fundamentals = context.fundamentals or {}
        if not fundamentals:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["fundamentals_missing"],
                details={},
            )
        return gate_result(self.gate_id, passed=True, details={"keys": list(fundamentals.keys())[:20]})


class ValuationGate:
    gate_id = "valuation"
    order = 7

    def evaluate(self, context: DecisionContext) -> GateResult:
        status = context.valuation_status
        # available/approved allow analysis to continue; add requires approved later.
        if status in {"available", "approved", "approved_for_personal_use"}:
            return gate_result(
                self.gate_id,
                passed=True,
                details={"valuation_status": status},
            )
        return gate_result(
            self.gate_id,
            passed=False,
            severity="high",
            blockers=["valuation_not_available"],
            details={"valuation_status": status, "note": "Add reviews require approved valuation."},
        )


class PortfolioFitGate:
    gate_id = "portfolio_fit"
    order = 8

    def evaluate(self, context: DecisionContext) -> GateResult:
        fit = context.portfolio_fit or {}
        policy = context.policy or {}
        max_weight = float(policy.get("max_single_stock_weight", 12.0))
        weight = float(
            fit.get("weight")
            or context.position.get("portfolio_weight")
            or context.position.get("weight")
            or 0
        )
        over = bool(fit.get("over_concentrated")) or weight > max_weight
        if over:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="high",
                blockers=["over_concentrated"],
                details={"weight": weight, "max_single_stock_weight": max_weight},
            )
        if not context.add_capacity_available:
            return gate_result(
                self.gate_id,
                passed=True,
                details={"add_capacity_available": False, "weight": weight},
            )
        return gate_result(self.gate_id, passed=True, details={"weight": weight})


class TaxGate:
    gate_id = "tax"
    order = 9

    def evaluate(self, context: DecisionContext) -> GateResult:
        tax = context.tax or {}
        status = str(tax.get("methodology_status") or tax.get("status") or "unknown")
        # Fail closed: unknown/missing tax evidence cannot pass.
        if status in {
            "withheld",
            "withheld_lot_inputs_unavailable",
            "failed",
            "unknown",
            "incomplete",
            "",
        }:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["tax_inputs_incomplete"],
                details={"status": status or "unknown"},
            )
        if not tax:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["tax_inputs_incomplete"],
                details={"status": "missing"},
            )
        lot_count = int(tax.get("lot_count") or 0)
        if lot_count <= 0 and status not in {"available", "experimental", "approved"}:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["tax_lots_missing"],
                details={"status": status, "lot_count": lot_count},
            )
        details = {
            "status": status,
            "lot_count": lot_count,
            "short_term_lots": tax.get("short_term_lots"),
            "long_term_lots": tax.get("long_term_lots"),
        }
        return gate_result(self.gate_id, passed=True, details=details)


class LiquidityGate:
    gate_id = "liquidity"
    order = 10

    def evaluate(self, context: DecisionContext) -> GateResult:
        liquidity = context.liquidity or {}
        if not liquidity:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["liquidity_incomplete"],
                details={"status": "missing"},
            )
        if liquidity.get("status") in {"withheld", "failed", "incomplete", "unknown"}:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["liquidity_incomplete"],
                details=liquidity,
            )
        return gate_result(self.gate_id, passed=True, details=liquidity)


class MethodologyGate:
    gate_id = "methodology"
    order = 11

    def evaluate(self, context: DecisionContext) -> GateResult:
        versions = context.methodology_versions or {}
        if not versions:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=["methodology_unbound"],
                details={"note": "no_methodology_versions_bound"},
            )
        withheld = [
            mid
            for mid, status in versions.items()
            if str(status).lower() in {"withheld", "retired", "unknown"}
        ]
        if withheld:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="high",
                blockers=["methodology_withheld"],
                details={"versions": versions, "withheld": withheld},
            )
        return gate_result(self.gate_id, passed=True, details={"versions": versions})


class ImplementationGate:
    gate_id = "implementation"
    order = 12

    def evaluate(self, context: DecisionContext) -> GateResult:
        blockers: list[str] = []
        tax = context.tax or {}
        liquidity = context.liquidity or {}
        tax_status = tax.get("methodology_status") or tax.get("status")
        if tax_status in {
            "withheld",
            "withheld_lot_inputs_unavailable",
            "failed",
            None,
            "unknown",
            "incomplete",
            "",
        }:
            blockers.append("tax_not_implementation_ready")
        if not liquidity or liquidity.get("status") in {
            "withheld",
            "failed",
            "incomplete",
            "unknown",
            None,
        }:
            blockers.append("liquidity_not_implementation_ready")
        if context.valuation_status in {"withheld", "experimental", "unknown", ""}:
            # Adds cannot be implementation-ready without approved valuation.
            blockers.append("valuation_not_implementation_ready")
        if blockers:
            return gate_result(
                self.gate_id,
                passed=False,
                severity="medium",
                blockers=blockers,
                details={"implementation_ready": False},
            )
        return gate_result(self.gate_id, passed=True, details={"implementation_ready": True})
