from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import postgres_available


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM users LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _row_to_user(row: dict[str, Any]) -> dict[str, str]:
    return {
        "email": row["email"].lower(),
        "name": row["name"],
        "password_hash": row["password_hash"],
        "role": row["role"],
        "token_version": str(row.get("token_version", 0)),
    }


def load_all_users() -> dict[str, dict[str, str]] | None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("user read", table_available=_table_available())
    elif not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text("SELECT email, name, password_hash, role, token_version FROM users")
        ).mappings().all()
    return {_row_to_user(dict(row))["email"]: _row_to_user(dict(row)) for row in rows}


def get_user(email: str) -> dict[str, str] | None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("user read", table_available=_table_available())
    elif not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT email, name, password_hash, role, token_version
                FROM users
                WHERE lower(email) = lower(:email)
                """
            ),
            {"email": email},
        ).mappings().first()
    if not row:
        return None
    return _row_to_user(dict(row))


def upsert_user(email: str, user: dict[str, str]) -> None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("user persistence", table_available=_table_available())
    elif not _table_available():
        return

    from app.db.session import SessionLocal

    normalized = email.lower()
    now = _utc_now()
    token_version = int(user.get("token_version", "0"))
    with SessionLocal() as session:
        existing = session.execute(
            text("SELECT id FROM users WHERE lower(email) = lower(:email)"),
            {"email": normalized},
        ).first()
        if existing:
            session.execute(
                text(
                    """
                    UPDATE users
                    SET name = :name,
                        password_hash = :password_hash,
                        role = :role,
                        token_version = :token_version,
                        updated_at = :updated_at
                    WHERE lower(email) = lower(:email)
                    """
                ),
                {
                    "email": normalized,
                    "name": user.get("name", normalized),
                    "password_hash": user["password_hash"],
                    "role": user.get("role", "viewer"),
                    "token_version": token_version,
                    "updated_at": now,
                },
            )
        else:
            session.execute(
                text(
                    """
                    INSERT INTO users (
                        email, password_hash, name, role, token_version, created_at, updated_at
                    ) VALUES (
                        :email, :password_hash, :name, :role, :token_version, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "email": normalized,
                    "password_hash": user["password_hash"],
                    "name": user.get("name", normalized),
                    "role": user.get("role", "viewer"),
                    "token_version": token_version,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        session.commit()


OWNER_BOOTSTRAP_LOCK = 90210


def bootstrap_owner_transactionally(email: str, password_hash: str, name: str) -> dict[str, str]:
    from fastapi import HTTPException

    if settings.persistence_backend != "postgres":
        raise HTTPException(status_code=503, detail="Transactional bootstrap requires Postgres persistence")
    require_postgres_persistence("owner bootstrap", table_available=_table_available())

    from app.db.session import SessionLocal

    normalized = email.lower()
    now = _utc_now()
    try:
        with SessionLocal.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": OWNER_BOOTSTRAP_LOCK})
            existing_owner = session.execute(text("SELECT 1 FROM users WHERE role = 'owner' LIMIT 1")).first()
            if existing_owner:
                raise HTTPException(status_code=409, detail="An owner account already exists")
            existing_user = session.execute(
                text("SELECT 1 FROM users WHERE lower(email) = lower(:email)"),
                {"email": normalized},
            ).first()
            if existing_user:
                raise HTTPException(status_code=409, detail="User already exists")

            user_row = session.execute(
                text(
                    """
                    INSERT INTO users (
                        email, password_hash, name, role, token_version, created_at, updated_at
                    ) VALUES (
                        :email, :password_hash, :name, 'owner', 0, :created_at, :updated_at
                    )
                    RETURNING id, email, name, password_hash, role, token_version
                    """
                ),
                {
                    "email": normalized,
                    "password_hash": password_hash,
                    "name": name,
                    "created_at": now,
                    "updated_at": now,
                },
            ).mappings().one()
            session.execute(
                text(
                    """
                    INSERT INTO user_account_access (
                        user_id, external_account_id, access_level, granted_by_user_id, created_at
                    ) VALUES (
                        :user_id, '*', 'read', :user_id, :created_at
                    )
                    ON CONFLICT ON CONSTRAINT uq_user_account_access_user_account DO NOTHING
                    """
                ),
                {"user_id": user_row["id"], "created_at": now},
            )
            return _row_to_user(dict(user_row))
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Owner bootstrap persistence failed: {exc}") from exc


def owner_exists() -> bool:
    require_postgres_persistence("owner existence check", table_available=_table_available())
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        return bool(
            session.execute(
                text("SELECT 1 FROM users WHERE role = 'owner' LIMIT 1")
            ).first()
        )


def update_user_role(email: str, role: str) -> dict[str, str] | None:
    require_postgres_persistence("user role update", table_available=_table_available())
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                UPDATE users
                SET role = :role,
                    token_version = token_version + 1,
                    updated_at = :updated_at
                WHERE lower(email) = lower(:email)
                RETURNING email, name, password_hash, role, token_version
                """
            ),
            {
                "email": email.lower(),
                "role": role,
                "updated_at": _utc_now(),
            },
        ).mappings().first()

        if row is None:
            session.rollback()
            return None

        session.commit()
        return _row_to_user(dict(row))


def bump_token_version(email: str) -> int:
    require_postgres_persistence("token revocation", table_available=_table_available())
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                UPDATE users
                SET token_version = token_version + 1,
                    updated_at = :updated_at
                WHERE lower(email) = lower(:email)
                RETURNING token_version
                """
            ),
            {
                "email": email.lower(),
                "updated_at": _utc_now(),
            },
        ).first()

        if row is None:
            session.rollback()
            raise LookupError("User not found")

        session.commit()
        return int(row[0])


def assert_bootstrap_owner_available() -> None:
    if not _table_available():
        return

    from fastapi import HTTPException

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(90210)"))
        existing = session.execute(text("SELECT 1 FROM users WHERE role = 'owner' LIMIT 1")).first()
        if existing:
            raise HTTPException(status_code=409, detail="An owner account already exists")
