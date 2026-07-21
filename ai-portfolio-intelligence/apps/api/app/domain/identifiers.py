"""Opaque identifier helpers."""

from __future__ import annotations

from typing import NewType
from uuid import uuid4

DecisionId = NewType("DecisionId", str)
EvidenceId = NewType("EvidenceId", str)


def new_decision_id() -> DecisionId:
    return DecisionId(f"dec_{uuid4().hex}")


def new_evidence_id() -> EvidenceId:
    return EvidenceId(f"ev_{uuid4().hex}")
