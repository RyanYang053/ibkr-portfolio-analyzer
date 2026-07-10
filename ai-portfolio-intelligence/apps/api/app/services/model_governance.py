from __future__ import annotations

from app.services.methodology_registry import MethodologyRecord


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
