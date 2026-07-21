"""Decision evaluation context assembled from evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.schemas.evidence import EvidenceRef


class EvaluationMode(str, Enum):
    """Explicit point-in-time evaluation mode (plan §15.4 / P0.4).

    LIVE_PROVISIONAL may use currently available evidence and may synthesize evidence
    that lacks an available_at timestamp (flagged provisional). HISTORICAL_REPLAY must
    fail closed on missing availability or future-data leakage and must never recover.
    """

    LIVE_PROVISIONAL = "live_provisional"
    HISTORICAL_REPLAY = "historical_replay"


@dataclass
class DecisionContext:
    account_id: str
    instrument_key: str
    symbol: str
    as_of: datetime
    evidence_cutoff: datetime
    position: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    thesis: dict[str, Any] = field(default_factory=dict)
    thesis_status: str = "unknown"
    risk: dict[str, Any] = field(default_factory=dict)
    portfolio_fit: dict[str, Any] = field(default_factory=dict)
    valuation_status: str = "withheld"
    valuation: dict[str, Any] = field(default_factory=dict)
    tax: dict[str, Any] = field(default_factory=dict)
    liquidity: dict[str, Any] = field(default_factory=dict)
    fundamentals: dict[str, Any] = field(default_factory=dict)
    lens_ensemble: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    financial_plan: dict[str, Any] = field(default_factory=dict)
    hard_risk_breach: bool = False
    hard_policy_breach: bool = False
    add_capacity_available: bool = True
    supportive_quality_evidence: bool = False
    methodology_versions: dict[str, str] = field(default_factory=dict)
    calculation_run_ids: list[str] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)
    previous_outcome: str | None = None
    previous_packet_id: str | None = None
    source_integrity_ok: bool = True
    evaluation_mode: EvaluationMode = EvaluationMode.LIVE_PROVISIONAL
