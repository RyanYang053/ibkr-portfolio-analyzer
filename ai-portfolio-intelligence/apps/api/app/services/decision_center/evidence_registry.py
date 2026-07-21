"""Evidence registry — resolve and hash context evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.product_contract import EvidenceQuality
from app.schemas.decision_context import DecisionContext
from app.schemas.evidence import EvidenceRef


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ref(
    *,
    evidence_type: str,
    provider: str,
    payload: Any,
    context: DecisionContext,
    quality: EvidenceQuality = EvidenceQuality.AVAILABLE,
    provisional: bool = False,
) -> EvidenceRef:
    now = context.as_of if context.as_of.tzinfo else context.as_of.replace(tzinfo=timezone.utc)
    return EvidenceRef(
        evidence_id=f"ev_{uuid4().hex[:16]}",
        evidence_type=evidence_type,
        provider=provider,
        account_id=context.account_id,
        instrument_key=context.instrument_key,
        observed_at=now,
        effective_at=now,
        available_at=now,
        quality_status=quality,
        content_sha256=_sha(payload),
        provisional=provisional,
        methodology_id=None,
        methodology_version=None,
        calculation_run_id=(context.calculation_run_ids[0] if context.calculation_run_ids else None),
    )


class EvidenceRegistry:
    def resolve_context_evidence(self, context: DecisionContext) -> list[EvidenceRef]:
        if context.evidence:
            return list(context.evidence)
        refs: list[EvidenceRef] = []
        mapping = [
            ("position_snapshot", "broker", context.position),
            ("thesis_version", "user", context.thesis),
            ("portfolio_risk_run", "risk_engine", context.risk),
            ("fundamental_snapshot", "fundamentals", context.fundamentals),
            ("valuation_run", "valuation", context.valuation or {"status": context.valuation_status}),
            ("tax_lot_report", "tax", context.tax),
            ("policy_version", "policy", context.policy),
            ("lens_ensemble", "investor_lenses", context.lens_ensemble),
            ("data_quality", "data_quality", context.data_quality),
        ]
        for evidence_type, provider, payload in mapping:
            if payload:
                quality = EvidenceQuality.AVAILABLE
                provisional = False
                if evidence_type == "valuation_run" and context.valuation_status in {
                    "withheld",
                    "experimental",
                }:
                    quality = (
                        EvidenceQuality.WITHHELD
                        if context.valuation_status == "withheld"
                        else EvidenceQuality.EXPERIMENTAL
                    )
                    provisional = True
                refs.append(
                    _ref(
                        evidence_type=evidence_type,
                        provider=provider,
                        payload=payload,
                        context=context,
                        quality=quality,
                        provisional=provisional,
                    )
                )
        return refs
