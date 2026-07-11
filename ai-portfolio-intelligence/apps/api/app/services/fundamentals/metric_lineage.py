from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from app.schemas.domain import FundamentalFieldLineage


def source_id_from_row(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("concept", "")),
        str(row.get("unit", "")),
        str(row.get("start", "")),
        str(row.get("end", "")),
        str(row.get("accn", "")),
        str(row.get("fp", "")),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def row_to_field_lineage(
    metric: str,
    row: dict[str, Any],
    *,
    derivation: str = "reported",
    value: float | None = None,
    source_ids: list[str] | None = None,
) -> FundamentalFieldLineage:
    resolved_value = float(value if value is not None else row["value"])
    return FundamentalFieldLineage(
        metric=metric,
        concept=str(row.get("concept", metric)),
        unit=str(row.get("unit", "USD")),
        value=resolved_value,
        start_date=_parse_date(row.get("start")),
        end_date=_parse_date(row.get("end")),
        filed_date=_parse_date(row.get("filed")),
        accepted_at=_parse_accepted(row.get("accepted")),
        accession=row.get("accn"),
        form=row.get("form"),
        fiscal_year=row.get("fy"),
        fiscal_period=row.get("fp"),
        source_hash=hash_payload(row),
        derivation=derivation,
        source_ids=source_ids or [source_id_from_row(row)],
    )


def lineage_from_rows(
    metric: str,
    rows: list[dict[str, Any]],
    *,
    derivation: str,
    value: float,
) -> FundamentalFieldLineage:
    primary = rows[-1]
    return FundamentalFieldLineage(
        metric=metric,
        concept=str(primary.get("concept", metric)),
        unit=str(primary.get("unit", "USD")),
        value=value,
        start_date=_parse_date(rows[0].get("start")),
        end_date=_parse_date(primary.get("end")),
        filed_date=_parse_date(primary.get("filed")),
        accepted_at=_parse_accepted(primary.get("accepted")),
        accession=primary.get("accn"),
        form=primary.get("form"),
        fiscal_year=primary.get("fy"),
        fiscal_period=primary.get("fp"),
        source_hash=hash_payload({"rows": rows, "value": value}),
        derivation=derivation,
        source_ids=[source_id_from_row(row) for row in rows],
    )


def hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def persist_metric_observation(
    *,
    symbol: str,
    metric: str,
    as_of_date: date,
    period_start: date | None,
    period_end: date | None,
    value: float,
    unit: str,
    derivation: str,
    source_observation_ids: list[str],
    calculation_version: str = "1.0.0",
) -> None:
    from app.db.fundamental_metric_repo import persist_fundamental_metric_observation

    persist_fundamental_metric_observation(
        symbol=symbol,
        metric=metric,
        as_of_date=as_of_date,
        period_start=period_start,
        period_end=period_end,
        value=value,
        unit=unit,
        derivation=derivation,
        source_observation_ids=source_observation_ids,
        source_hash=hash_payload(
            {
                "symbol": symbol,
                "metric": metric,
                "as_of_date": as_of_date.isoformat(),
                "value": value,
                "derivation": derivation,
                "source_observation_ids": source_observation_ids,
            }
        ),
        calculation_version=calculation_version,
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_accepted(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None
