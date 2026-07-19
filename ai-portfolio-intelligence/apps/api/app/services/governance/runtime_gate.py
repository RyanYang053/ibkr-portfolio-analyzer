from __future__ import annotations

from datetime import datetime, timezone

from app.db.methodology_version_repo import get_effective_methodology_version
from app.services.model_governance import MethodologyNotApproved, require_methodology_status


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def gate_production_output(
    methodology_id: str,
    *,
    allowed_statuses: set[str] | None = None,
    experimental_label: str = "experimental",
) -> dict[str, object]:
    allowed = allowed_statuses or {"approved"}
    try:
        record = require_methodology_status(methodology_id, allowed_statuses=allowed)
    except MethodologyNotApproved as exc:
        return {
            "allowed": False,
            "approval_status": experimental_label,
            "methodology_id": methodology_id,
            "reason": str(exc),
        }
    except Exception as exc:
        # Fail closed without turning methodology gating into an API 500.
        return {
            "allowed": False,
            "approval_status": experimental_label,
            "methodology_id": methodology_id,
            "reason": f"methodology gate unavailable: {exc}",
        }
    return {
        "allowed": True,
        "approval_status": record.status,
        "methodology_id": record.methodology_id,
        "version": record.version,
        "code_sha": record.code_sha,
        "artifact_sha256": record.artifact_sha256,
        "effective_at": record.effective_at.isoformat(),
    }


def methodology_lineage_for_response(methodology_id: str) -> dict[str, str]:
    record = get_effective_methodology_version(methodology_id, utc_now())
    if record is None:
        return {
            "methodology_id": methodology_id,
            "approval_status": "missing",
        }
    return {
        "methodology_id": record.methodology_id,
        "version": record.version,
        "approval_status": record.status,
        "effective_date": record.effective_at.date().isoformat(),
        "code_sha": record.code_sha or "not_recorded",
        "validation_artifact_hash": record.artifact_sha256 or "not_recorded",
    }


def enforce_or_mark_experimental(
    methodology_id: str,
    payload: dict[str, object],
    *,
    production: bool,
) -> dict[str, object]:
    gate = gate_production_output(methodology_id)
    payload = dict(payload)
    payload["methodology_gate"] = gate
    if production and not gate.get("allowed"):
        payload["status"] = "withheld_unapproved_methodology"
        payload["professional_language_allowed"] = False
    else:
        payload["professional_language_allowed"] = bool(gate.get("allowed"))
    return payload
