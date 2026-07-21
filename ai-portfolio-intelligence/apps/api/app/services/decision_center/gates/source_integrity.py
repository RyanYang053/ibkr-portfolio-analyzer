from __future__ import annotations

from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult
from app.services.decision_center.gates.base import gate_result


class SourceIntegrityGate:
    gate_id = "source_integrity"
    order = 1

    def evaluate(self, context: DecisionContext) -> GateResult:
        if not context.source_integrity_ok:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="critical",
                blockers=["source_integrity_failed"],
                details={"source_integrity_ok": False},
            )
        synthetic = any(getattr(e, "synthetic_demo", False) for e in context.evidence)
        if synthetic:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="critical",
                blockers=["synthetic_demo_evidence"],
                details={"synthetic_demo": True},
            )
        return gate_result(self.gate_id, passed=True)
