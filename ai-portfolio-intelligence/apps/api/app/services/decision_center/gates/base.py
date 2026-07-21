"""Gate protocol and shared helpers."""

from __future__ import annotations

from typing import Protocol

from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult


class DecisionGate(Protocol):
    gate_id: str
    order: int

    def evaluate(self, context: DecisionContext) -> GateResult:
        ...


def gate_result(
    gate_id: str,
    *,
    passed: bool,
    terminal: bool = False,
    severity: str = "info",
    status: str = "evaluated",
    blockers: list[str] | None = None,
    details: dict | None = None,
) -> GateResult:
    return GateResult(
        gate_id=gate_id,
        passed=passed,
        terminal=terminal,
        severity=severity if not passed else "info",
        status="terminal" if terminal else status,
        blockers=list(blockers or []),
        details=dict(details or {}),
    )
