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


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_stale(record: dict[str, Any], as_of: datetime | str) -> bool:
    """Live-mode staleness (plan §15.4): evidence past its stale_after/expires_at.

    Staleness is a *flag* for live provisional evaluation — it is not lookahead and
    does not, on its own, reject the evidence.
    """
    as_of_dt = _parse_dt(as_of)
    if as_of_dt is None:
        return False
    for field in ("stale_after", "expires_at"):
        boundary = _parse_dt(record.get(field))
        if boundary is not None and as_of_dt > boundary:
            return True
    return False


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
            # Annotate (a copy) with staleness so live callers can flag it provisional.
            usable.append({**record, "pit_stale": is_stale(record, as_of)})
        else:
            rejected.append({**record, "pit_guard": check})
    return usable, rejected


def stale_evidence_ids(usable: list[dict[str, Any]]) -> list[str]:
    """Evidence ids among usable records that are stale (for provisional flagging)."""
    return [
        str(r.get("evidence_id") or r.get("field") or "evidence")
        for r in usable
        if r.get("pit_stale")
    ]
