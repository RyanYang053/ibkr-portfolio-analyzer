"""Persist methodology approvals to SQL tables (0032/0034) when available."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.sql_dialect import json_cast


def _payload_json(payload: dict[str, Any] | None) -> str:
    import json

    return json.dumps(payload or {}, sort_keys=True)


def write_personal_methodology_approval(
    *,
    methodology_id: str,
    version: str,
    approver: str,
    status: str,
    notes: str | None,
    approved_at: datetime,
    payload: dict[str, Any] | None = None,
) -> bool:
    if settings.persistence_backend not in {"postgres", "sqlite"}:
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO personal_methodology_approvals
                        (methodology_id, version, approver, status, notes, payload_json, approved_at)
                    VALUES
                        (:methodology_id, :version, :approver, :status, :notes, {json_cast("payload_json")}, :approved_at)
                    ON CONFLICT (methodology_id, version) DO UPDATE SET
                        approver = EXCLUDED.approver,
                        status = EXCLUDED.status,
                        notes = EXCLUDED.notes,
                        payload_json = EXCLUDED.payload_json,
                        approved_at = EXCLUDED.approved_at
                    """
                    if settings.persistence_backend == "postgres"
                    else f"""
                    INSERT INTO personal_methodology_approvals
                        (methodology_id, version, approver, status, notes, payload_json, approved_at)
                    VALUES
                        (:methodology_id, :version, :approver, :status, :notes, {json_cast("payload_json")}, :approved_at)
                    ON CONFLICT (methodology_id, version) DO UPDATE SET
                        approver = excluded.approver,
                        status = excluded.status,
                        notes = excluded.notes,
                        payload_json = excluded.payload_json,
                        approved_at = excluded.approved_at
                    """
                ),
                {
                    "methodology_id": methodology_id,
                    "version": version,
                    "approver": approver,
                    "status": status,
                    "notes": notes,
                    "payload_json": _payload_json(payload),
                    "approved_at": approved_at,
                },
            )
            session.commit()
        return True
    except (SQLAlchemyError, Exception):
        return False


def write_valuation_model_approval(
    *,
    model_id: str,
    version: str,
    status: str,
    approver: str | None,
    approved_at: datetime | None,
    payload: dict[str, Any] | None = None,
) -> bool:
    if settings.persistence_backend not in {"postgres", "sqlite"}:
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO valuation_model_approvals
                        (model_id, version, status, approver, approved_at, payload_json)
                    VALUES
                        (:model_id, :version, :status, :approver, :approved_at, {json_cast("payload_json")})
                    ON CONFLICT (model_id, version) DO UPDATE SET
                        status = EXCLUDED.status,
                        approver = EXCLUDED.approver,
                        approved_at = EXCLUDED.approved_at,
                        payload_json = EXCLUDED.payload_json
                    """
                    if settings.persistence_backend == "postgres"
                    else f"""
                    INSERT INTO valuation_model_approvals
                        (model_id, version, status, approver, approved_at, payload_json)
                    VALUES
                        (:model_id, :version, :status, :approver, :approved_at, {json_cast("payload_json")})
                    ON CONFLICT (model_id, version) DO UPDATE SET
                        status = excluded.status,
                        approver = excluded.approver,
                        approved_at = excluded.approved_at,
                        payload_json = excluded.payload_json
                    """
                ),
                {
                    "model_id": model_id,
                    "version": version,
                    "status": status,
                    "approver": approver,
                    "approved_at": approved_at,
                    "payload_json": _payload_json(payload),
                },
            )
            session.commit()
        return True
    except (SQLAlchemyError, Exception):
        return False
