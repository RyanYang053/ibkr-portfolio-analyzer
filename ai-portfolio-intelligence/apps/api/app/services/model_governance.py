from __future__ import annotations

from datetime import datetime, timezone

from app.db.methodology_version_repo import MethodologyVersion, get_effective_methodology_version
from app.services.methodology_registry import MethodologyRecord


class MethodologyNotApproved(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_methodology_status(
    methodology_id: str,
    *,
    allowed_statuses: set[str] | None = None,
) -> MethodologyVersion:
    allowed = allowed_statuses or {"approved"}
    record = get_effective_methodology_version(methodology_id, utc_now())
    if record is None:
        from app.db.methodology_repo import load_methodology_registry

        fallback = next(
            (item for item in load_methodology_registry() if item.methodology_id == methodology_id),
            None,
        )
        if fallback is None:
            raise MethodologyNotApproved(f"{methodology_id}: no effective version")
        if fallback.approval_status not in allowed:
            raise MethodologyNotApproved(f"{methodology_id}: status={fallback.approval_status}")
        if fallback.approval_status == "approved":
            raise MethodologyNotApproved(f"{methodology_id}: validation evidence incomplete")
        raise MethodologyNotApproved(f"{methodology_id}: status={fallback.approval_status}")

    if record.status not in allowed:
        raise MethodologyNotApproved(f"{methodology_id}: status={record.status}")
    if record.status == "approved" and (not record.code_sha or not record.artifact_sha256):
        raise MethodologyNotApproved(f"{methodology_id}: validation evidence incomplete")
    return record


def can_promote_to_production(record: MethodologyRecord) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if record.approval_status != "approved":
        blockers.append(f"approval_status is {record.approval_status}")
    if not record.owner:
        blockers.append("owner is required")
    if not record.version:
        blockers.append("version is required")
    if not record.independent_validation_fixture:
        blockers.append("independent validation fixture is required")
    if not record.known_limitations:
        blockers.append("known limitations must be documented")
    return len(blockers) == 0, blockers


def model_change_requires_rollback(record: MethodologyRecord, target_version: str) -> bool:
    if record.rollback_version and target_version == record.rollback_version:
        return True
    return record.approval_status == "withheld"


def coverage_summary_for_page(data_quality: dict[str, str], exclusions: list[str] | None = None) -> dict[str, object]:
    missing = [key for key, value in data_quality.items() if value in {"missing", "insufficient", "withheld", "not_computed"}]
    return {
        "coverage_items": data_quality,
        "missing_items": missing,
        "exclusions": exclusions or [],
        "status": "partial" if missing else "complete",
    }
