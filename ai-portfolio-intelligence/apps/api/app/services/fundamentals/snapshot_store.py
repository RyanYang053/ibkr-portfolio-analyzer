from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from threading import Lock
from typing import Optional

from app.schemas.domain import FundamentalSnapshot, FundamentalSnapshotRecord

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_FILE_LOCK = Lock()


def _store_path(symbol: str) -> str:
    safe = symbol.upper().replace("/", "_")
    return os.path.join(DATA_DIR, f"fundamentals_{safe}.json")


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


def save_snapshot_record(record: FundamentalSnapshotRecord) -> FundamentalSnapshotRecord:
    path = _store_path(record.symbol)
    existing: list[dict] = []
    if os.path.exists(path):
        with _FILE_LOCK, open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
    keyed = {
        f"{item['as_of_date']}": item
        for item in existing
        if isinstance(item, dict) and item.get("as_of_date")
    }
    keyed[record.as_of_date.isoformat()] = record.model_dump(mode="json")
    merged = sorted(keyed.values(), key=lambda item: item["as_of_date"])
    _atomic_write(path, merged)
    return record


def list_snapshot_records(symbol: str) -> list[FundamentalSnapshotRecord]:
    path = _store_path(symbol)
    if not os.path.exists(path):
        return []
    with _FILE_LOCK, open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return [FundamentalSnapshotRecord(**item) for item in raw]


def get_point_in_time_fundamentals(symbol: str, as_of: date) -> Optional[FundamentalSnapshot]:
    """Return the latest fundamentals known on or before the as-of date."""
    records = list_snapshot_records(symbol)
    eligible = [record for record in records if record.as_of_date <= as_of]
    if not eligible:
        return None
    latest = sorted(eligible, key=lambda record: record.as_of_date)[-1]
    return latest.snapshot


def seed_walk_forward_demo_records(symbol: str, base_snapshot: FundamentalSnapshot) -> list[FundamentalSnapshotRecord]:
    """Create quarterly point-in-time snapshots for walk-forward calibration demos."""
    from datetime import timedelta

    records: list[FundamentalSnapshotRecord] = []
    for quarter in range(4):
        as_of = date.today() - timedelta(days=90 * quarter)
        adjusted = base_snapshot.model_copy(
            update={
                "report_date": as_of,
                "revenue_growth_yoy": max(-0.2, base_snapshot.revenue_growth_yoy - 0.03 * quarter),
                "source": f"{base_snapshot.source}_pit_q{quarter}",
            }
        )
        record = FundamentalSnapshotRecord(
            symbol=symbol.upper(),
            as_of_date=as_of,
            snapshot=adjusted,
            point_in_time=True,
            source=adjusted.source,
        )
        records.append(save_snapshot_record(record))
    return records
