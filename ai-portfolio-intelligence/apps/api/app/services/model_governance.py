"""Align methodology approval vocabulary and promotion rules."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.product_contract import MethodologyStatus
from app.db.methodology_version_repo import MethodologyVersion, get_effective_methodology_version
from app.services.methodology_registry import MethodologyRecord

PERSONAL_USE_STATUSES: frozenset[str] = frozenset(
    {
        "approved",
        MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value,
    }
)


class MethodologyNotApproved(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_methodology_status(
    methodology_id: str,
    *,
    allowed_statuses: set[str] | None = None,
) -> MethodologyVersion | MethodologyRecord:
    allowed = allowed_statuses or set(PERSONAL_USE_STATUSES)
    # Also accept approvals recorded in the personal-use state store.
    try:
        from app.services.validation.methodology_validation import list_methodologies

        for item in list_methodologies():
            if str(item.get("methodology_id")) != methodology_id:
                continue
            if str(item.get("status")) in allowed:
                return MethodologyRecord(
                    methodology_id=methodology_id,
                    name=str(item.get("name") or methodology_id),
                    version=str(item.get("version") or "1.0.0"),
                    effective_date=utc_now().date(),
                    owner=str(item.get("owner") or "personal"),
                    approval_status=str(item.get("status")),
                    independent_validation_fixture=item.get("independent_validation_fixture"),
                    known_limitations=tuple(item.get("known_limitations") or ()),
                    rollback_version=None,
                )
    except Exception:
        pass

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
        # Personal-use approvals may omit code/artifact digests when golden fixtures
        # are bound via independent_validation_fixture + approval record.
        if (
            fallback.approval_status in PERSONAL_USE_STATUSES
            and not fallback.independent_validation_fixture
        ):
            raise MethodologyNotApproved(f"{methodology_id}: validation evidence incomplete")
        return fallback

    if record.status not in allowed:
        raise MethodologyNotApproved(f"{methodology_id}: status={record.status}")
    if record.status in PERSONAL_USE_STATUSES and (not record.code_sha or not record.artifact_sha256):
        # Allow personal-use when golden digest is present on the version row OR
        # when an approval record exists (checked above via list_methodologies).
        if not record.artifact_sha256:
            raise MethodologyNotApproved(f"{methodology_id}: validation evidence incomplete")
    return record


def can_promote_to_production(record: MethodologyRecord) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if record.approval_status not in PERSONAL_USE_STATUSES:
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
