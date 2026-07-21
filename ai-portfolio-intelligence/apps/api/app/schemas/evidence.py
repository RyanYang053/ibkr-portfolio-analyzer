"""Evidence reference schema for Decision Packets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.product_contract import EvidenceQuality


class EvidenceRef(BaseModel):
    evidence_id: str
    evidence_type: str
    provider: str
    source_record_id: str | None = None
    account_id: str | None = None
    instrument_key: str | None = None
    observed_at: datetime
    effective_at: datetime | None = None
    available_at: datetime
    expires_at: datetime | None = None
    stale_after: datetime | None = None
    quality_status: EvidenceQuality | str
    methodology_id: str | None = None
    methodology_version: str | None = None
    calculation_run_id: str | None = None
    content_sha256: str
    provisional: bool = False
    synthetic_demo: bool = False


class EvidenceRecord(EvidenceRef):
    """Persisted evidence row with optional payload."""

    payload: dict[str, Any] = Field(default_factory=dict)
