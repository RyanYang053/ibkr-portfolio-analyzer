from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.state_store import postgres_available
from app.schemas.domain import FundamentalSnapshot, FundamentalSnapshotRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM fundamental_snapshot_records LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _row_to_record(row: dict[str, Any]) -> FundamentalSnapshotRecord:
    payload = json.loads(row["payload_json"])
    snapshot = FundamentalSnapshot(**payload["snapshot"]) if "snapshot" in payload else FundamentalSnapshot(**payload)
    ingested_at = row["ingested_at"]
    filing_date = row.get("filing_date")
    return FundamentalSnapshotRecord(
        symbol=row["symbol"],
        as_of_date=row["as_of_date"],
        snapshot=snapshot,
        point_in_time=bool(row["point_in_time"]),
        source=row["source"],
        report_period=row.get("report_period"),
        filing_date=filing_date,
        ingested_at=ingested_at,
        synthetic_demo=bool(row.get("synthetic_demo", False)),
    )


def upsert_snapshot_record(record: FundamentalSnapshotRecord) -> None:
    if not _table_available():
        return

    from app.db.session import SessionLocal

    ingested_at = record.ingested_at or _utc_now()
    payload_text = json.dumps(record.model_dump(mode="json"))
    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO fundamental_snapshot_records (
                    symbol, as_of_date, point_in_time, source, filing_date,
                    report_period, synthetic_demo, payload_json, ingested_at
                ) VALUES (
                    :symbol, :as_of_date, :point_in_time, :source, :filing_date,
                    :report_period, :synthetic_demo, :payload_json, :ingested_at
                )
                ON CONFLICT ON CONSTRAINT uq_fundamental_snapshot_records_identity
                DO UPDATE SET
                    filing_date = EXCLUDED.filing_date,
                    report_period = EXCLUDED.report_period,
                    synthetic_demo = EXCLUDED.synthetic_demo,
                    payload_json = EXCLUDED.payload_json
                """
            ),
            {
                "symbol": record.symbol.upper(),
                "as_of_date": record.as_of_date,
                "point_in_time": record.point_in_time,
                "source": record.source,
                "filing_date": record.filing_date,
                "report_period": record.report_period,
                "synthetic_demo": record.synthetic_demo,
                "payload_json": payload_text,
                "ingested_at": ingested_at,
            },
        )
        session.commit()


def list_snapshot_records(symbol: str, include_synthetic_demo: bool = False) -> list[FundamentalSnapshotRecord] | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT symbol, as_of_date, point_in_time, source, filing_date,
                       report_period, synthetic_demo, payload_json, ingested_at
                FROM fundamental_snapshot_records
                WHERE symbol = :symbol
                ORDER BY as_of_date ASC, ingested_at ASC
                """
            ),
            {"symbol": symbol.upper()},
        ).mappings().all()

    records = [_row_to_record(dict(row)) for row in rows]
    if include_synthetic_demo:
        return records
    return [record for record in records if not record.synthetic_demo and record.point_in_time]
