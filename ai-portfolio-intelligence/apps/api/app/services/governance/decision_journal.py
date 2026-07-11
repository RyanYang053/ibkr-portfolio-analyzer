from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.db.state_store import get_state_store


class DecisionJournalEntry(BaseModel):
    entry_id: str
    user_id: str
    account_id: str
    symbol: str | None = None
    action: str
    priority: str = "medium"
    rationale: str
    expected_benefit: str = ""
    risk_change: str = ""
    tax_estimate: str = ""
    transaction_cost: str = ""
    alternative: str = ""
    no_trade_option: str = ""
    calculation_run_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    review_date: str | None = None
    status: str = "proposed"


def append_decision_journal_entry(entry: DecisionJournalEntry) -> DecisionJournalEntry:
    store = get_state_store()
    key = f"{entry.user_id}:{entry.account_id}:{entry.entry_id}"
    store.write_json("decision_journal", key, entry.model_dump(mode="json"))
    return entry


def list_decision_journal_entries(user_id: str, account_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    store = get_state_store()
    namespace_path = store._path("decision_journal", "placeholder") if hasattr(store, "_path") else None
    _ = namespace_path
    # JsonStateStore has no list API; use account-scoped aggregate key.
    aggregate = store.read_json("decision_journal", f"{user_id}:{account_id}", default=[])
    if not isinstance(aggregate, list):
        return []
    return aggregate[-limit:]


def record_journal_from_ai_report(
    *,
    user_id: str,
    account_id: str,
    report: dict[str, Any],
    calculation_run_ids: list[str] | None = None,
) -> list[DecisionJournalEntry]:
    entries: list[DecisionJournalEntry] = []
    moves = report.get("ranked_moves") or report.get("holdings_to_watch") or []
    if isinstance(moves, list):
        for index, move in enumerate(moves[:10]):
            if isinstance(move, dict):
                symbol = move.get("symbol")
                action = str(move.get("action", "review"))
                rationale = str(move.get("reason", move.get("rationale", "AI portfolio memo recommendation")))
            else:
                symbol = str(move)
                action = "watch"
                rationale = "Flagged in AI portfolio memo"
            entry = DecisionJournalEntry(
                entry_id=f"ai-{account_id}-{index}",
                user_id=user_id,
                account_id=account_id,
                symbol=symbol,
                action=action,
                rationale=rationale,
                calculation_run_ids=calculation_run_ids or [],
            )
            entries.append(append_decision_journal_entry(entry))

    if entries:
        store = get_state_store()
        aggregate_key = f"{user_id}:{account_id}"
        existing = store.read_json("decision_journal", aggregate_key, default=[])
        merged = (existing if isinstance(existing, list) else []) + [
            item.model_dump(mode="json") for item in entries
        ]
        store.write_json("decision_journal", aggregate_key, merged[-200:])
    return entries
