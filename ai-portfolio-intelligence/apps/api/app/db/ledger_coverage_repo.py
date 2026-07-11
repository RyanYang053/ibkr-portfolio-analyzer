from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.state_store import postgres_available
from app.services.portfolio.ledger_coverage import TransactionLedgerCoverage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM ledger_coverage_records LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def read_coverage(account_id: str) -> dict[str, Any] | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT payload_json
                FROM ledger_coverage_records
                WHERE account_id = :account_id
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"account_id": account_id},
        ).mappings().first()
    if not row:
        return None
    try:
        return json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None


def upsert_coverage(coverage: TransactionLedgerCoverage) -> None:
    if not _table_available():
        return

    from app.db.session import SessionLocal

    now = _utc_now()
    payload_text = json.dumps(coverage.model_dump(mode="json"))
    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO ledger_coverage_records (
                    account_id, source, coverage_start, coverage_end, status, payload_json, updated_at
                ) VALUES (
                    :account_id, :source, :coverage_start, :coverage_end, :status, :payload_json, :updated_at
                )
                ON CONFLICT ON CONSTRAINT uq_ledger_coverage_account_source
                DO UPDATE SET
                    coverage_start = EXCLUDED.coverage_start,
                    coverage_end = EXCLUDED.coverage_end,
                    status = EXCLUDED.status,
                    payload_json = EXCLUDED.payload_json,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "account_id": coverage.account_id,
                "source": coverage.source,
                "coverage_start": coverage.coverage_start,
                "coverage_end": coverage.coverage_end,
                "status": coverage.status,
                "payload_json": payload_text,
                "updated_at": now,
            },
        )
        session.commit()
