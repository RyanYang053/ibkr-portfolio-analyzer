from __future__ import annotations

from typing import Any, Optional

from app.schemas.domain import AccountSummary, Position
from app.services.broker.base import BrokerAdapter
from app.services.data_quality.validation import (
    prepare_professional_response,
    validate_and_gate_snapshot,
)
from app.services.portfolio.account_scope import resolve_portfolio_account_id

NON_PORTFOLIO_ACCOUNT_IDS = frozenset({"WATCHLIST_ONLY", "SYNTHETIC_RESEARCH"})


def is_portfolio_position(position: Position) -> bool:
    return position.account_id not in NON_PORTFOLIO_ACCOUNT_IDS


def load_portfolio_snapshot(
    adapter: BrokerAdapter,
    account_id: Optional[str] = None,
) -> tuple[str, AccountSummary, list[Position]]:
    active_id = resolve_portfolio_account_id(account_id, adapter)
    summary = adapter.get_account_summary(active_id)
    positions = adapter.get_positions(active_id)
    return active_id, summary, positions


def gate_professional_response(
    adapter: BrokerAdapter,
    account_id: Optional[str],
    result: Any,
) -> dict[str, Any]:
    _, summary, positions = load_portfolio_snapshot(adapter, account_id)
    validation = validate_and_gate_snapshot(summary, positions)
    return prepare_professional_response(result, summary, positions, validation)
