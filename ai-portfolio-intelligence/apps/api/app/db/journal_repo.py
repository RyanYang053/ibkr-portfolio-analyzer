"""Trade journal persistence (plan §10 / §17).

SQL-backed for sqlite/postgres; JSON state store for the json test backend.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.journal import JournalEntry

_NAMESPACE = "journal_entries"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def save_journal_entry(entry: JournalEntry) -> JournalEntry:
    now = _now()
    if entry.created_at is None:
        entry.created_at = now
    entry.updated_at = now
    payload = entry.model_dump(mode="json")

    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO journal_entries (
                        entry_id, account_id, instrument_id, symbol, trade_plan_id,
                        outcome_classification, realized_return, payload_json, created_at, updated_at
                    ) VALUES (
                        :entry_id, :account_id, :instrument_id, :symbol, :trade_plan_id,
                        :outcome, :realized_return, {json_cast("payload_json")}, :created_at, :updated_at
                    )
                    ON CONFLICT(entry_id) DO UPDATE SET
                        outcome_classification = excluded.outcome_classification,
                        realized_return = excluded.realized_return,
                        trade_plan_id = excluded.trade_plan_id,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "entry_id": entry.entry_id,
                    "account_id": entry.account_id,
                    "instrument_id": entry.instrument_id,
                    "symbol": entry.symbol,
                    "trade_plan_id": entry.trade_plan_id,
                    "outcome": entry.outcome_classification.value,
                    "realized_return": entry.realized_return,
                    "payload_json": json.dumps(payload),
                    "created_at": entry.created_at,
                    "updated_at": now,
                },
            )
            session.commit()
        return entry

    from app.db.state_store import get_state_store

    store = get_state_store()
    store.write_json(_NAMESPACE, entry.entry_id, payload)
    index = store.read_json(_NAMESPACE, f"index:{entry.account_id}", default={"ids": []}) or {"ids": []}
    ids = list(index.get("ids") or [])
    if entry.entry_id not in ids:
        ids.insert(0, entry.entry_id)
        store.write_json(_NAMESPACE, f"index:{entry.account_id}", {"ids": ids})
    return entry


def get_journal_entry(entry_id: str) -> JournalEntry | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM journal_entries WHERE entry_id = :eid"),
                {"eid": entry_id},
            ).scalar()
        if row is None:
            return None
        payload = row if isinstance(row, dict) else json.loads(row)
        return JournalEntry.model_validate(payload)

    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NAMESPACE, entry_id, default=None)
    return JournalEntry.model_validate(payload) if payload else None


def list_journal_entries(account_id: str, *, limit: int = 500) -> list[JournalEntry]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    "SELECT payload_json FROM journal_entries WHERE account_id = :account_id "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"account_id": account_id, "limit": limit},
            ).scalars().all()
        sql_out: list[JournalEntry] = []
        for row in rows:
            payload = row if isinstance(row, dict) else json.loads(row)
            sql_out.append(JournalEntry.model_validate(payload))
        return sql_out

    from app.db.state_store import get_state_store

    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"ids": []}) or {"ids": []}
    out: list[JournalEntry] = []
    for eid in (index.get("ids") or [])[:limit]:
        payload = store.read_json(_NAMESPACE, str(eid), default=None)
        if payload:
            out.append(JournalEntry.model_validate(payload))
    return out
