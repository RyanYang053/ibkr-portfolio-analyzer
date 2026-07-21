"""Research queue orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.research_candidate_repo import ResearchCandidateRepository
from app.services.research.candidate_ranker import rank_candidates
from app.services.research.catalyst_calendar import build_catalyst_calendar, days_until_next_catalyst
from app.services.research.change_detector import detect_changes
from app.services.research.research_priority import score_research_priority, sort_by_priority


class ResearchQueueService:
    def __init__(self, repo: ResearchCandidateRepository | None = None) -> None:
        self.repo = repo or ResearchCandidateRepository()

    def build_queue(
        self,
        *,
        account_id: str,
        holdings: list[dict[str, Any]],
        watchlist: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        symbols = [str(h.get("symbol")) for h in holdings if h.get("symbol")]
        calendar = build_catalyst_calendar(symbols)
        enriched: list[dict[str, Any]] = []
        for holding in holdings:
            previous = self.repo.latest_snapshot(account_id, str(holding.get("instrument_key") or holding.get("symbol")))
            changes = detect_changes(previous, holding)
            catalyst_days = days_until_next_catalyst(calendar, str(holding.get("symbol")))
            priority = score_research_priority(
                change_codes=[str(c.get("change_code")) for c in changes],
                catalyst_days=catalyst_days,
                decision_outcome=str(holding.get("outcome") or holding.get("action") or "monitor"),
                data_stale=bool(holding.get("data_stale")),
            )
            row = {
                **holding,
                "account_id": account_id,
                "changes": changes,
                "catalyst_days": catalyst_days,
                **priority,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.repo.save_candidate(row)
            enriched.append(row)

        ranked = rank_candidates(enriched, watchlist=watchlist)
        return {
            "account_id": account_id,
            "queue": sort_by_priority(ranked),
            "catalyst_calendar": calendar,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "order_generated": False,
        }

    def list_queue(self, account_id: str) -> list[dict[str, Any]]:
        return sort_by_priority(self.repo.list_for_account(account_id))
