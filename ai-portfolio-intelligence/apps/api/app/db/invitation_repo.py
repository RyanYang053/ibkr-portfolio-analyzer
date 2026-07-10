from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.user_repo import _row_to_user, _table_available, _utc_now


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _invitations_table_available() -> bool:
    if not _table_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM user_invitations LIMIT 1"))
        return True
    except Exception:
        return False


def create_invitation(
    email: str,
    role: str,
    invited_by: str,
    *,
    ttl_hours: int = 72,
) -> tuple[str, dict[str, Any]]:
    require_postgres_persistence(
        "invitation creation",
        table_available=_invitations_table_available(),
    )
    from app.db.session import SessionLocal

    plaintext = secrets.token_urlsafe(32)
    digest = _digest(plaintext)
    normalized = email.lower()
    now = _utc_now()
    expires_at = now + timedelta(hours=ttl_hours)

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO user_invitations (
                    token_digest, email, role, invited_by_email, expires_at, created_at
                ) VALUES (
                    :token_digest, :email, :role, :invited_by_email, :expires_at, :created_at
                )
                """
            ),
            {
                "token_digest": digest,
                "email": normalized,
                "role": role,
                "invited_by_email": invited_by.lower(),
                "expires_at": expires_at,
                "created_at": now,
            },
        )
        session.commit()

    metadata = {
        "email": normalized,
        "role": role,
        "invited_by": invited_by.lower(),
        "expires_at": expires_at.isoformat(),
        "accepted_at": None,
    }
    return plaintext, metadata


def get_invitation_by_token(token: str) -> dict[str, Any] | None:
    require_postgres_persistence(
        "invitation read",
        table_available=_invitations_table_available(),
    )
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT email, role, invited_by_email, expires_at, accepted_at
                FROM user_invitations
                WHERE token_digest = :token_digest
                  AND accepted_at IS NULL
                  AND expires_at > :now
                """
            ),
            {"token_digest": _digest(token), "now": _utc_now()},
        ).mappings().first()
    if not row:
        return None
    return {
        "email": row["email"],
        "role": row["role"],
        "invited_by": row["invited_by_email"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "accepted_at": row["accepted_at"].isoformat() if row["accepted_at"] else None,
    }


def consume_invitation_and_create_user(
    *,
    token: str,
    name: str,
    password_hash: str,
) -> dict[str, str] | None:
    require_postgres_persistence(
        "invitation acceptance",
        table_available=_invitations_table_available(),
    )
    from app.db.session import SessionLocal

    digest = _digest(token)
    now = _utc_now()

    with SessionLocal.begin() as session:
        invitation = session.execute(
            text(
                """
                SELECT id, email, role, invited_by_email
                FROM user_invitations
                WHERE token_digest = :token_digest
                  AND accepted_at IS NULL
                  AND expires_at > :now
                FOR UPDATE
                """
            ),
            {"token_digest": digest, "now": now},
        ).mappings().first()
        if invitation is None:
            return None

        existing = session.execute(
            text("SELECT 1 FROM users WHERE lower(email) = lower(:email)"),
            {"email": invitation["email"]},
        ).first()
        if existing:
            return None

        user_row = session.execute(
            text(
                """
                INSERT INTO users (
                    email, password_hash, name, role, token_version, created_at, updated_at
                ) VALUES (
                    :email, :password_hash, :name, :role, 0, :created_at, :updated_at
                )
                RETURNING email, name, password_hash, role, token_version
                """
            ),
            {
                "email": invitation["email"],
                "password_hash": password_hash,
                "name": name,
                "role": invitation["role"],
                "created_at": now,
                "updated_at": now,
            },
        ).mappings().one()

        session.execute(
            text(
                """
                UPDATE user_invitations
                SET accepted_at = :accepted_at
                WHERE id = :id
                """
            ),
            {"accepted_at": now, "id": invitation["id"]},
        )

    return _row_to_user(dict(user_row))


def list_invitations() -> list[dict[str, Any]]:
    require_postgres_persistence(
        "invitation list",
        table_available=_invitations_table_available(),
    )
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT email, role, invited_by_email, expires_at, accepted_at
                FROM user_invitations
                ORDER BY created_at DESC
                """
            )
        ).mappings().all()

    return [
        {
            "email": row["email"],
            "role": row["role"],
            "invited_by": row["invited_by_email"],
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            "accepted_at": row["accepted_at"].isoformat() if row["accepted_at"] else None,
        }
        for row in rows
    ]
