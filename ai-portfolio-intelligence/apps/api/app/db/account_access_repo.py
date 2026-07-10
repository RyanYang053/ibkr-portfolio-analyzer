from __future__ import annotations

from datetime import datetime, timezone

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
            session.execute(text("SELECT 1 FROM user_account_access LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _user_id(session, email: str) -> int | None:
    row = session.execute(
        text("SELECT id FROM users WHERE lower(email) = lower(:email)"),
        {"email": email.lower()},
    ).first()
    return int(row[0]) if row else None


def load_all_access() -> dict[str, list[str]] | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT u.email, a.external_account_id
                FROM user_account_access a
                JOIN users u ON u.id = a.user_id
                ORDER BY u.email ASC, a.external_account_id ASC
                """
            )
        ).mappings().all()

    access: dict[str, list[str]] = {}
    for row in rows:
        email = row["email"].lower()
        access.setdefault(email, []).append(row["external_account_id"])
    return access


def list_accessible_accounts(user_email: str) -> list[str] | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        user_id = _user_id(session, user_email)
        if user_id is None:
            return []
        rows = session.execute(
            text(
                """
                SELECT external_account_id
                FROM user_account_access
                WHERE user_id = :user_id
                ORDER BY external_account_id ASC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
    return [row["external_account_id"] for row in rows]


def grant_account_access(user_email: str, account_id: str, *, granted_by_user_id: int | None = None) -> None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("account access grant", table_available=_table_available())
    elif not _table_available():
        return

    from app.db.session import SessionLocal

    now = _utc_now()
    with SessionLocal() as session:
        user_id = _user_id(session, user_email)
        if user_id is None:
            return
        session.execute(
            text(
                """
                INSERT INTO user_account_access (
                    user_id, external_account_id, access_level, granted_by_user_id, created_at
                ) VALUES (
                    :user_id, :external_account_id, 'read', :granted_by_user_id, :created_at
                )
                ON CONFLICT ON CONSTRAINT uq_user_account_access_user_account DO NOTHING
                """
            ),
            {
                "user_id": user_id,
                "external_account_id": account_id,
                "granted_by_user_id": granted_by_user_id,
                "created_at": now,
            },
        )
        session.commit()


def revoke_account_access(user_email: str, account_id: str) -> None:
    if not _table_available():
        return

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        user_id = _user_id(session, user_email)
        if user_id is None:
            return
        session.execute(
            text(
                """
                DELETE FROM user_account_access
                WHERE user_id = :user_id AND external_account_id = :external_account_id
                """
            ),
            {"user_id": user_id, "external_account_id": account_id},
        )
        session.commit()
