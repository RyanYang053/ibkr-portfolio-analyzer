"""Approved replacement / core instruments from plan + watchlist only."""

from __future__ import annotations

from typing import Any


CORE_ETF_CANDIDATES = (
    "VOO",
    "VTI",
    "IVV",
    "SPY",
    "QQQ",
    "IWM",
    "VXUS",
    "BND",
    "AGG",
)


def build_replacement_universe(
    *,
    plan: dict[str, Any] | None = None,
    watchlist_symbols: list[str] | None = None,
    held_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Return buy candidates the user already approved via plan/watchlist — never invent tickers."""
    policy = (plan or {}).get("policy") or {}
    preferred = [str(s).upper() for s in (policy.get("preferred_asset_classes") or [])]
    prohibited = {str(s).upper() for s in (policy.get("prohibited_symbols") or [])}
    watchlist = [str(s).upper() for s in (watchlist_symbols or [])]
    held = {str(s).upper() for s in (held_symbols or [])}

    # Prefer explicit core ETF from policy constraints when present.
    constraints = policy.get("constraints") if isinstance(policy.get("constraints"), dict) else {}
    configured_core = constraints.get("core_etf") or policy.get("core_etf")
    core_etf = str(configured_core).upper() if configured_core else None

    etf_pool = [s for s in watchlist if s in CORE_ETF_CANDIDATES and s not in prohibited]
    if core_etf is None and etf_pool:
        core_etf = etf_pool[0]
    if core_etf is None:
        # Only suggest a default core if it appears on the watchlist or preferred list.
        for candidate in CORE_ETF_CANDIDATES:
            if candidate in watchlist or candidate in preferred:
                core_etf = candidate
                break

    buy_candidates = [
        s
        for s in watchlist
        if s not in prohibited and s not in held
    ]
    return {
        "core_etf": core_etf,
        "buy_candidates": buy_candidates[:50],
        "prohibited_symbols": sorted(prohibited),
        "preferred_asset_classes": preferred,
        "source": "plan_and_watchlist",
        "order_generated": False,
        "notes": "Universe limited to user plan/watchlist. No broker order generation.",
    }
