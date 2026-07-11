from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import get_state_store, postgres_available


class BrokerSyncBatch(BaseModel):
    batch_id: str
    account_id: str
    source: str
    row_count: int = 0
    period_start: date | None = None
    period_end: date | None = None
    imported_sections: list[str] = Field(default_factory=list)
    rejected_row_count: int = 0
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM broker_sync_batches LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def create_broker_sync_batch(
    *,
    account_id: str,
    source: str,
    row_count: int,
    period_start: date | None = None,
    period_end: date | None = None,
    imported_sections: list[str] | None = None,
    rejected_row_count: int = 0,
) -> BrokerSyncBatch:
    batch = BrokerSyncBatch(
        batch_id=str(uuid.uuid4()),
        account_id=account_id,
        source=source,
        row_count=row_count,
        period_start=period_start,
        period_end=period_end,
        imported_sections=imported_sections or [],
        rejected_row_count=rejected_row_count,
    )
    payload = batch.model_dump(mode="json")
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("broker sync batch write", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO broker_sync_batches (
                        id, account_id, source, row_count, period_start, period_end, payload_json, ingested_at
                    ) VALUES (
                        :id, :account_id, :source, :row_count, :period_start, :period_end, :payload_json, :ingested_at
                    )
                    """
                ),
                {
                    "id": batch.batch_id,
                    "account_id": account_id,
                    "source": source,
                    "row_count": row_count,
                    "period_start": period_start,
                    "period_end": period_end,
                    "payload_json": json.dumps(payload),
                    "ingested_at": batch.ingested_at,
                },
            )
            session.commit()
        return batch

    get_state_store().write_json("broker_sync_batches", f"{account_id}:{batch.batch_id}", payload)
    return batch


def read_broker_sync_batch(account_id: str, batch_id: str) -> BrokerSyncBatch | None:
    if settings.persistence_backend == "postgres":
        from app.db.postgres_guard import require_postgres_read

        require_postgres_read("broker sync batch read", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT payload_json
                    FROM broker_sync_batches
                    WHERE id = :batch_id AND account_id = :account_id
                    """
                ),
                {"batch_id": batch_id, "account_id": account_id},
            ).fetchone()
        if row is None:
            return None
        try:
            return BrokerSyncBatch(**json.loads(row.payload_json))
        except json.JSONDecodeError:
            return None

    payload = get_state_store().read_json("broker_sync_batches", f"{account_id}:{batch_id}")
    return BrokerSyncBatch(**payload) if isinstance(payload, dict) else None
