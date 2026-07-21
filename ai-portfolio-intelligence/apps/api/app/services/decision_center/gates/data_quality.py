from __future__ import annotations

from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult
from app.services.decision_center.gates.base import gate_result


class DataQualityGate:
    gate_id = "data_quality"
    order = 2

    def evaluate(self, context: DecisionContext) -> GateResult:
        dq = context.data_quality or {}
        missing = list(dq.get("missing") or [])
        status = dq.get("status")
        if status != "ok" or missing:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="critical",
                blockers=["data_quality"] + [f"missing:{m}" for m in missing],
                details=dq,
            )
        stale = list(dq.get("stale") or [])
        if stale:
            return gate_result(
                self.gate_id,
                passed=False,
                terminal=True,
                severity="high",
                blockers=["stale_data"] + stale,
                details=dq,
            )
        return gate_result(self.gate_id, passed=True, details=dq)
