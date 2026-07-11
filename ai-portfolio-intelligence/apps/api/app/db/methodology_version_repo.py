from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import postgres_available


@dataclass(frozen=True)
class MethodologyVersion:
    methodology_id: str
    name: str
    version: str
    effective_at: datetime
    status: str
    owner: str
    code_sha: str | None
    artifact_sha256: str | None
    validator: str | None = None
    approver: str | None = None
    approved_at: datetime | None = None
    fixture_version: str | None = None
    data_version: str | None = None
    tolerance_json: dict[str, Any] | None = None
    known_limitations: tuple[str, ...] = ()
    rollback_version: str | None = None
    supersedes_version: str | None = None
    independent_validation_fixture: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tables_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM methodology_versions LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def governance_tables_available() -> bool:
    return _tables_available()


def require_governance_tables(operation: str) -> None:
    require_postgres_persistence(operation, table_available=_tables_available())


def _row_to_version(row: dict[str, Any]) -> MethodologyVersion:
    limitations = row.get("known_limitations_json") or []
    if isinstance(limitations, str):
        limitations = json.loads(limitations)
    tolerance = row.get("tolerance_json") or {}
    if isinstance(tolerance, str):
        tolerance = json.loads(tolerance)
    return MethodologyVersion(
        methodology_id=str(row["methodology_id"]),
        name=str(row.get("name") or row["methodology_id"]),
        version=str(row["version"]),
        effective_at=row["effective_at"],
        status=str(row["status"]),
        owner=str(row["owner"]),
        code_sha=row.get("code_sha"),
        artifact_sha256=row.get("artifact_sha256"),
        validator=row.get("validator"),
        approver=row.get("approver"),
        approved_at=row.get("approved_at"),
        fixture_version=row.get("fixture_version"),
        data_version=row.get("data_version"),
        tolerance_json=tolerance,
        known_limitations=tuple(str(item) for item in limitations),
        rollback_version=row.get("rollback_version"),
        supersedes_version=row.get("supersedes_version"),
        independent_validation_fixture=row.get("independent_validation_fixture"),
    )


def get_effective_methodology_version(methodology_id: str, as_of: datetime) -> MethodologyVersion | None:
    if not _tables_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT mv.*, m.name
                FROM methodology_versions mv
                JOIN methodologies m ON m.methodology_id = mv.methodology_id
                WHERE mv.methodology_id = :methodology_id
                  AND mv.effective_at <= :as_of
                ORDER BY mv.effective_at DESC, mv.created_at DESC
                LIMIT 1
                """
            ),
            {"methodology_id": methodology_id, "as_of": as_of},
        ).mappings().first()
    if not row:
        return None
    return _row_to_version(dict(row))


def list_methodology_versions(*, status: str | None = None) -> list[MethodologyVersion]:
    if not _tables_available():
        return []

    from app.db.session import SessionLocal

    query = """
        SELECT mv.*, m.name
        FROM methodology_versions mv
        JOIN methodologies m ON m.methodology_id = mv.methodology_id
    """
    params: dict[str, Any] = {}
    if status is not None:
        query += " WHERE mv.status = :status"
        params["status"] = status
    query += " ORDER BY mv.methodology_id, mv.effective_at DESC"

    with SessionLocal() as session:
        rows = session.execute(text(query), params).mappings().all()
    return [_row_to_version(dict(row)) for row in rows]


def upsert_methodology_version(record: MethodologyVersion) -> None:
    require_governance_tables("methodology version write")
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO methodologies (methodology_id, name, owner)
                VALUES (:methodology_id, :name, :owner)
                ON CONFLICT (methodology_id)
                DO UPDATE SET name = EXCLUDED.name, owner = EXCLUDED.owner
                """
            ),
            {
                "methodology_id": record.methodology_id,
                "name": record.name,
                "owner": record.owner,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO methodology_versions (
                    methodology_id, version, effective_at, code_sha, status, owner,
                    validator, approver, approved_at, fixture_version, data_version,
                    tolerance_json, artifact_sha256, known_limitations_json,
                    rollback_version, supersedes_version
                ) VALUES (
                    :methodology_id, :version, :effective_at, :code_sha, :status, :owner,
                    :validator, :approver, :approved_at, :fixture_version, :data_version,
                    CAST(:tolerance_json AS jsonb), :artifact_sha256, CAST(:known_limitations_json AS jsonb),
                    :rollback_version, :supersedes_version
                )
                ON CONFLICT ON CONSTRAINT uq_methodology_versions_identity
                DO NOTHING
                """
            ),
            {
                "methodology_id": record.methodology_id,
                "version": record.version,
                "effective_at": record.effective_at,
                "code_sha": record.code_sha,
                "status": record.status,
                "owner": record.owner,
                "validator": record.validator,
                "approver": record.approver,
                "approved_at": record.approved_at,
                "fixture_version": record.fixture_version,
                "data_version": record.data_version,
                "tolerance_json": json.dumps(record.tolerance_json or {}),
                "artifact_sha256": record.artifact_sha256,
                "known_limitations_json": json.dumps(list(record.known_limitations)),
                "rollback_version": record.rollback_version,
                "supersedes_version": record.supersedes_version,
            },
        )
        session.commit()


def seed_default_methodology_versions(defaults: list[MethodologyVersion]) -> None:
    if settings.persistence_backend != "postgres" or not _tables_available():
        return
    for record in defaults:
        upsert_methodology_version(record)
