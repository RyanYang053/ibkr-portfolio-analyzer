from __future__ import annotations

from typing import Any

from app.schemas.domain import FundamentalSnapshot


def resolve_sector_from_yahoo(
    sector: str,
    *,
    asset_profile: dict[str, Any] | None = None,
    summary_profile: dict[str, Any] | None = None,
) -> str:
    if sector and sector != "Unknown":
        return sector
    for profile in (asset_profile or {}, summary_profile or {}):
        candidate = profile.get("sector")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return sector or "Unknown"


def enrich_sector_fields(
    snapshot: FundamentalSnapshot,
    sector: str,
    *,
    stats: dict[str, Any] | None = None,
    financial_data: dict[str, Any] | None = None,
) -> FundamentalSnapshot:
    """Do not fabricate sector accounting metrics from generic Yahoo fields."""
    _ = (sector, stats, financial_data)
    return snapshot
