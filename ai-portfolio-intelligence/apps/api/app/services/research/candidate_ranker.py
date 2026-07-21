"""Rank research candidates from holdings / watchlist."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.services.research.research_priority import score_research_priority, sort_by_priority


def rank_candidates(
    holdings: list[dict[str, Any]],
    *,
    watchlist: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for holding in holdings:
        outcome = str(holding.get("outcome") or holding.get("action") or "monitor")
        changes = list(holding.get("change_reason_codes") or holding.get("changes") or [])
        if changes and isinstance(changes[0], dict):
            changes = [c.get("change_code") or c.get("code") or "" for c in changes]
        priority = score_research_priority(
            change_codes=[str(c) for c in changes if c],
            decision_outcome=outcome.lower().replace(" ", "_"),
            data_stale=bool(holding.get("data_stale")),
        )
        candidates.append(
            {
                "candidate_id": holding.get("candidate_id") or f"cand_{uuid4().hex[:10]}",
                "instrument_key": holding.get("instrument_key") or holding.get("symbol"),
                "symbol": holding.get("symbol"),
                "source": "holding",
                "outcome": outcome,
                **priority,
            }
        )

    for item in watchlist or []:
        priority = score_research_priority(change_codes=[], decision_outcome="monitor")
        candidates.append(
            {
                "candidate_id": f"cand_{uuid4().hex[:10]}",
                "instrument_key": item.get("instrument_key") or item.get("symbol"),
                "symbol": item.get("symbol"),
                "source": "watchlist",
                "outcome": "monitor",
                **priority,
            }
        )

    return sort_by_priority(candidates)
