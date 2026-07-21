"""Point-in-time data availability guard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def assert_point_in_time(
    *,
    observed_at: datetime | str | None,
    available_at: datetime | str | None,
    as_of: datetime | str | None,
    field_name: str = "value",
) -> dict[str, Any]:
    """Fail closed when data was not available at the decision as_of timestamp."""

    def _parse(value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    as_of_dt = _parse(as_of)
    available_dt = _parse(available_at)
    observed_dt = _parse(observed_at)

    if as_of_dt is None:
        return {
            "ok": False,
            "field": field_name,
            "reason": "missing_as_of",
            "fail_closed": True,
        }
    if available_dt is None:
        return {
            "ok": False,
            "field": field_name,
            "reason": "missing_available_at",
            "fail_closed": True,
        }
    if available_dt > as_of_dt:
        return {
            "ok": False,
            "field": field_name,
            "reason": "lookahead_leakage",
            "available_at": available_dt.isoformat(),
            "as_of": as_of_dt.isoformat(),
            "fail_closed": True,
        }
    return {
        "ok": True,
        "field": field_name,
        "observed_at": observed_dt.isoformat() if observed_dt else None,
        "available_at": available_dt.isoformat(),
        "as_of": as_of_dt.isoformat(),
        "fail_closed": True,
    }


def filter_usable_evidence(
    records: list[dict[str, Any]],
    *,
    as_of: datetime | str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    usable: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for record in records:
        check = assert_point_in_time(
            observed_at=record.get("observed_at"),
            available_at=record.get("available_at"),
            as_of=as_of,
            field_name=str(record.get("evidence_id") or record.get("field") or "evidence"),
        )
        if check["ok"]:
            usable.append(record)
        else:
            rejected.append({**record, "pit_guard": check})
    return usable, rejected
