from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM tax_affiliated_accounts LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _read_index() -> dict[str, dict[str, Any]]:
    payload = get_state_store().read_json("tax_affiliated_accounts", "index", default={})
    return payload if isinstance(payload, dict) else {}


def upsert_affiliated_account(
    *,
    household_id: str,
    account_id: str,
    relationship: str,
    effective_date: date,
    source: str = "manual",
) -> dict[str, Any]:
    record = {
        "household_id": household_id,
        "account_id": account_id,
        "relationship": relationship,
        "effective_date": effective_date.isoformat(),
        "source": source,
    }
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("tax affiliated account write", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO tax_affiliated_accounts (
                        household_id, account_id, relationship, effective_date, source
                    ) VALUES (
                        :household_id, :account_id, :relationship, :effective_date, :source
                    )
                    """
                ),
                {
                    "household_id": household_id,
                    "account_id": account_id,
                    "relationship": relationship,
                    "effective_date": effective_date,
                    "source": source,
                },
            )
            session.commit()
        return record

    index = _read_index()
    index[f"{household_id}:{account_id}"] = record
    get_state_store().write_json("tax_affiliated_accounts", "index", index)
    return record


def list_affiliated_account_ids(
    account_id: str,
    *,
    as_of: date | None = None,
) -> list[str]:
    """Return other account IDs in the same household as ``account_id``."""
    as_of = as_of or date.today()
    if settings.persistence_backend == "postgres" and _table_available():
        require_postgres_read("tax affiliated account read", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            households = session.execute(
                text(
                    """
                    SELECT DISTINCT household_id
                    FROM tax_affiliated_accounts
                    WHERE account_id = :account_id
                      AND effective_date <= :as_of
                    """
                ),
                {"account_id": account_id, "as_of": as_of},
            ).fetchall()
            household_ids = [str(row.household_id) for row in households]
            if not household_ids:
                return []
            rows = session.execute(
                text(
                    """
                    SELECT DISTINCT account_id
                    FROM tax_affiliated_accounts
                    WHERE household_id = ANY(:household_ids)
                      AND account_id <> :account_id
                      AND effective_date <= :as_of
                    """
                ),
                {
                    "household_ids": household_ids,
                    "account_id": account_id,
                    "as_of": as_of,
                },
            ).fetchall()
        return [str(row.account_id) for row in rows]

    index = _read_index()
    household_id_set: set[str] = {
        str(item.get("household_id"))
        for item in index.values()
        if isinstance(item, dict)
        and item.get("account_id") == account_id
        and date.fromisoformat(str(item.get("effective_date", "1900-01-01"))) <= as_of
    }
    return sorted(
        {
            str(item["account_id"])
            for item in index.values()
            if isinstance(item, dict)
            and str(item.get("household_id")) in household_id_set
            and item.get("account_id") != account_id
            and date.fromisoformat(str(item.get("effective_date", "1900-01-01"))) <= as_of
        }
    )


def register_affiliated_household(
    household_id: str,
    account_ids: list[str],
    *,
    relationship: str = "affiliated",
    effective_date: date | None = None,
    source: str = "manual",
) -> list[dict[str, Any]]:
    effective = effective_date or date.today()
    return [
        upsert_affiliated_account(
            household_id=household_id,
            account_id=account_id,
            relationship=relationship,
            effective_date=effective,
            source=source,
        )
        for account_id in account_ids
    ]
