from __future__ import annotations

from datetime import date

from app.core.config import settings
from app.db.methodology_version_repo import (
    governance_tables_available,
    list_methodology_versions,
    require_governance_tables,
    seed_default_methodology_versions,
)
from app.services.methodology_registry import DEFAULT_METHODOLOGIES, MethodologyRecord, default_methodology_versions


def load_methodology_registry() -> list[MethodologyRecord]:
    if settings.persistence_backend == "postgres":
        if governance_tables_available():
            versions = list_methodology_versions()
            if versions:
                return [
                    MethodologyRecord(
                        methodology_id=item.methodology_id,
                        name=item.name,
                        version=item.version,
                        effective_date=item.effective_at.date(),
                        owner=item.owner,
                        approval_status=item.status,
                        independent_validation_fixture=item.independent_validation_fixture,
                        known_limitations=item.known_limitations,
                        rollback_version=item.rollback_version,
                    )
                    for item in versions
                ]
        else:
            require_governance_tables("methodology registry read")
        return list(DEFAULT_METHODOLOGIES)

    from app.db.legacy_bridge import read_json_with_legacy

    payload = read_json_with_legacy("methodology_registry", "records", None, default=None)
    if not isinstance(payload, list):
        return list(DEFAULT_METHODOLOGIES)

    records: list[MethodologyRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            records.append(
                MethodologyRecord(
                    methodology_id=str(item["methodology_id"]),
                    name=str(item["name"]),
                    version=str(item["version"]),
                    effective_date=date.fromisoformat(str(item["effective_date"])),
                    owner=str(item["owner"]),
                    approval_status=str(item["approval_status"]),
                    independent_validation_fixture=item.get("independent_validation_fixture"),
                    known_limitations=tuple(str(limit) for limit in item.get("known_limitations", [])),
                    rollback_version=item.get("rollback_version"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return records or list(DEFAULT_METHODOLOGIES)


def save_methodology_registry(records: list[MethodologyRecord]) -> None:
    if settings.persistence_backend == "postgres":
        require_governance_tables("methodology registry write")
        seed_default_methodology_versions(default_methodology_versions())
        return

    from app.db.legacy_bridge import write_json_state

    payload = [
        {
            "methodology_id": record.methodology_id,
            "name": record.name,
            "version": record.version,
            "effective_date": record.effective_date.isoformat(),
            "owner": record.owner,
            "approval_status": record.approval_status,
            "independent_validation_fixture": record.independent_validation_fixture,
            "known_limitations": list(record.known_limitations),
            "rollback_version": record.rollback_version,
        }
        for record in records
    ]
    write_json_state("methodology_registry", "records", payload)


def methodology_registry_available() -> bool:
    if settings.persistence_backend != "postgres":
        return True
    return governance_tables_available()
