"""Gate result schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GateResult(BaseModel):
    gate_id: str
    passed: bool
    terminal: bool = False
    severity: str = "info"
    status: str = "evaluated"
    blockers: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    opposing_evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
