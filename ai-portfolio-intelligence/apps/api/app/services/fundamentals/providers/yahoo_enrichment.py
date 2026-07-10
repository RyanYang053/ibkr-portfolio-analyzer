from __future__ import annotations

from typing import Any, Optional

from app.schemas.domain import FundamentalSnapshot


def _raw(stats: dict[str, Any], key: str) -> float | None:
    node = stats.get(key) or {}
    if not isinstance(node, dict):
        return None
    raw = node.get("raw")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


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
    stats = stats or {}
    financial_data = financial_data or {}
    updates: dict[str, float] = {}

    if sector == "Financials":
        price_to_book = _raw(stats, "priceToBook")
        return_on_equity = _raw(stats, "returnOnEquity")
        net_interest_margin = _raw(financial_data, "operatingMargins")
        if price_to_book is not None:
            updates["price_to_tangible_book"] = price_to_book
        if return_on_equity is not None:
            updates["return_on_equity"] = return_on_equity
        if net_interest_margin is not None:
            updates["net_interest_margin"] = net_interest_margin

    elif sector == "Real Estate":
        ffo_per_share = _raw(stats, "trailingEps")
        if ffo_per_share is not None and ffo_per_share > 0:
            updates["ffo_per_share"] = ffo_per_share
        operating_margin = _raw(financial_data, "operatingMargins")
        if operating_margin is not None:
            updates["occupancy_rate"] = min(0.99, max(0.85, 0.85 + operating_margin * 0.25))

    elif sector == "Utilities":
        rate_base_growth = _raw(financial_data, "revenueGrowth")
        allowed_roe = _raw(stats, "returnOnEquity")
        if rate_base_growth is not None:
            updates["rate_base_growth"] = rate_base_growth
        if allowed_roe is not None:
            updates["allowed_roe"] = allowed_roe

    elif sector == "Energy":
        ebitda = _raw(stats, "enterpriseToEbitda")
        if ebitda is not None and ebitda > 0:
            updates["fcf_yield"] = max(0.0, min(0.2, 1.0 / ebitda))

    elif sector == "Healthcare":
        return_on_equity = _raw(stats, "returnOnEquity")
        if return_on_equity is not None:
            updates["return_on_equity"] = return_on_equity

    elif sector in {"Industrials", "Materials"}:
        return_on_equity = _raw(stats, "returnOnEquity")
        operating_margin = _raw(financial_data, "operatingMargins")
        if return_on_equity is not None:
            updates["return_on_equity"] = return_on_equity
        if operating_margin is not None and sector == "Industrials":
            updates["rate_base_growth"] = operating_margin * 0.1

    if not updates:
        return snapshot
    return snapshot.model_copy(update=updates)
