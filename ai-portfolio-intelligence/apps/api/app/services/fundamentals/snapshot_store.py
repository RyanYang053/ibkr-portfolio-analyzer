from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timezone
from threading import Lock
from typing import Optional

from app.core.config import settings
from app.schemas.domain import FundamentalSnapshot, FundamentalSnapshotRecord

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_FILE_LOCK = Lock()
_STATE_NAMESPACE = "fundamental_snapshots"


def _store_path(symbol: str) -> str:
    safe = symbol.upper().replace("/", "_")
    return os.path.join(DATA_DIR, f"fundamentals_{safe}.json")


def _record_key(record: FundamentalSnapshotRecord) -> str:
    ingested = record.ingested_at.isoformat() if record.ingested_at else "unknown"
    return "|".join(
        [
            record.symbol.upper(),
            record.as_of_date.isoformat(),
            str(record.point_in_time),
            record.source,
            ingested,
        ]
    )


def _atomic_write(path: str, payload: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _FILE_LOCK:
        fd, temporary_path = tempfile.mkstemp(prefix="fundamentals_", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def _raw_records(symbol: str) -> list[dict]:
    # P0.2 / §16.1: SQLite is canonical under the shipped desktop backend; raw JSON
    # files are only used in pure ``json`` mode.
    if settings.persistence_backend == "sqlite":
        from app.db.state_store import get_state_store

        return list(get_state_store().read_json(_STATE_NAMESPACE, symbol.upper(), default=None) or [])
    path = _store_path(symbol)
    if not os.path.exists(path):
        return []
    with _FILE_LOCK, open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_records(symbol: str, merged: list[dict]) -> None:
    if settings.persistence_backend == "sqlite":
        from app.db.state_store import get_state_store

        get_state_store().write_json(_STATE_NAMESPACE, symbol.upper(), merged)
        return
    _atomic_write(_store_path(symbol), merged)


def _load_json_records(symbol: str) -> list[FundamentalSnapshotRecord]:
    return [FundamentalSnapshotRecord(**item) for item in _raw_records(symbol)]


def save_snapshot_record(record: FundamentalSnapshotRecord) -> FundamentalSnapshotRecord:
    if settings.persistence_backend == "postgres":
        from app.db.fundamental_snapshot_repo import upsert_snapshot_record

        upsert_snapshot_record(record)
        return record

    existing = _raw_records(record.symbol)
    keyed = {
        _record_key(FundamentalSnapshotRecord(**item)): item
        for item in existing
        if isinstance(item, dict) and item.get("symbol")
    }
    keyed[_record_key(record)] = record.model_dump(mode="json")
    merged = sorted(
        keyed.values(),
        key=lambda item: (item.get("as_of_date", ""), item.get("ingested_at", "")),
    )
    _write_records(record.symbol, merged)
    return record


def list_snapshot_records(symbol: str, include_synthetic_demo: bool = False) -> list[FundamentalSnapshotRecord]:
    if settings.persistence_backend == "postgres":
        from app.db.fundamental_snapshot_repo import list_snapshot_records as list_postgres_records

        records = list_postgres_records(symbol, include_synthetic_demo=include_synthetic_demo)
        if records is not None:
            return records

    records = _load_json_records(symbol)
    if include_synthetic_demo:
        return records
    return [record for record in records if not record.synthetic_demo and record.point_in_time]


def get_point_in_time_fundamentals(symbol: str, as_of: date, allow_synthetic_demo: bool = False) -> Optional[FundamentalSnapshot]:
    records = list_snapshot_records(symbol, include_synthetic_demo=allow_synthetic_demo)
    eligible = []
    for record in records:
        effective_date = record.filing_date or record.as_of_date
        if effective_date <= as_of and (record.point_in_time or (allow_synthetic_demo and record.synthetic_demo)):
            eligible.append((effective_date, record))
    if not eligible:
        return None
    latest = sorted(eligible, key=lambda item: item[0])[-1][1]
    return latest.snapshot


def seed_demo_fundamentals_records(symbol: str, base_snapshot: FundamentalSnapshot) -> list[FundamentalSnapshotRecord]:
    """Isolated demo-only records. Never used in live mode."""
    from datetime import timedelta

    records: list[FundamentalSnapshotRecord] = []
    for quarter in range(4):
        as_of = date.today() - timedelta(days=90 * quarter)
        adjusted = base_snapshot.model_copy(
            update={
                "report_date": as_of,
                "source": "synthetic_demo",
            }
        )
        record = FundamentalSnapshotRecord(
            symbol=symbol.upper(),
            as_of_date=as_of,
            snapshot=adjusted,
            point_in_time=True,
            source="synthetic_demo",
            report_period=adjusted.period,
            ingested_at=datetime.now(timezone.utc),
            synthetic_demo=True,
        )
        records.append(save_snapshot_record(record))
    return records
