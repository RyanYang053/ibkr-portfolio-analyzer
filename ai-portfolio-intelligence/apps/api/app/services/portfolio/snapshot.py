from __future__ import annotations

from typing import Any, Optional

from app.api.account_deps import resolve_authorized_account_ids
from app.api.auth_deps import Principal
from app.schemas.domain import AccountSummary, Position
from app.services.broker.base import BrokerAdapter
from app.services.data_quality.validation import (
    prepare_professional_response,
    validate_and_gate_snapshot,
)

NON_PORTFOLIO_ACCOUNT_IDS = frozenset({"WATCHLIST_ONLY", "SYNTHETIC_RESEARCH"})


def is_portfolio_position(position: Position) -> bool:
    return position.account_id not in NON_PORTFOLIO_ACCOUNT_IDS


def load_portfolio_snapshot(
    adapter: BrokerAdapter,
    principal: Principal,
    account_id: Optional[str] = None,
) -> tuple[str, AccountSummary, list[Position]]:
    allowed_ids = resolve_authorized_account_ids(adapter, principal, account_id)
    active_id = allowed_ids[0]
    summary = adapter.get_account_summary(active_id)
    positions = adapter.get_positions(active_id)
    return active_id, summary, positions


def gate_professional_response(
    adapter: BrokerAdapter,
    principal: Principal,
    account_id: Optional[str],
    result: Any,
    *,
    methodology_id: str | None = None,
) -> dict[str, Any]:
    _, summary, positions = load_portfolio_snapshot(adapter, principal, account_id)
    validation = validate_and_gate_snapshot(summary, positions)
    return prepare_professional_response(
        result,
        summary,
        positions,
        validation,
        methodology_id=methodology_id,
    )
