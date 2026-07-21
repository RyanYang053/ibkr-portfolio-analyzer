"""Match imported broker executions to a Trade Plan (plan §9.4).

Classifies completed transactions relative to a plan. Critically, an execution
that does not correspond to a plan is recorded as UNPLANNED — it is never assumed
to have been recommended by the system.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.schemas.execution_match import ExecutionMatch, MatchType
from app.schemas.trade_plan import TradePlan

_BUY_ACTIONS = {"buy"}
_SELL_ACTIONS = {"sell"}
_OPTION_ACTIONS = {"assignment": MatchType.OPTION_ASSIGNMENT, "exercise": MatchType.OPTION_EXERCISE}


def _plan_symbol(plan: TradePlan) -> str:
    return (plan.symbol or plan.instrument_id.split(":", 1)[0]).upper()


def match_executions(plan: TradePlan, transactions: list) -> ExecutionMatch:
    symbol = _plan_symbol(plan)
    increasing = plan.direction.value in {"buy", "add"}
    relevant_actions = _BUY_ACTIONS if increasing else _SELL_ACTIONS

    matched_txns = []
    executed_qty = 0.0
    match_types: set[MatchType] = set()
    notes: list[str] = []

    for txn in transactions:
        t_symbol = str(getattr(txn, "symbol", "")).upper()
        if t_symbol != symbol:
            continue
        action = str(getattr(txn, "action", "")).lower()
        created = plan.created_at
        t_time = getattr(txn, "event_timestamp", None) or getattr(txn, "trade_date", None)
        if created is not None and t_time is not None:
            t_dt = t_time if isinstance(t_time, datetime) else None
            if t_dt is not None and t_dt < created:
                continue  # predates the plan; not this plan's execution
        if action in _OPTION_ACTIONS:
            match_types.add(_OPTION_ACTIONS[action])
            matched_txns.append(str(getattr(txn, "transaction_id", "") or getattr(txn, "source_row_id", "")))
            continue
        if action == "corporate_action":
            match_types.add(MatchType.CORPORATE_ACTION)
            continue
        if action in relevant_actions:
            matched_txns.append(str(getattr(txn, "transaction_id", "") or getattr(txn, "source_row_id", "")))
            executed_qty += abs(float(getattr(txn, "quantity", 0) or 0))

    if not matched_txns:
        return ExecutionMatch(
            match_id=f"em_{uuid4().hex[:12]}",
            trade_plan_id=plan.trade_plan_id,
            account_id=plan.account_id,
            instrument_id=plan.instrument_id,
            symbol=symbol,
            match_types=[MatchType.NO_MATCH],
            matched=False,
            planned_quantity=plan.proposed_quantity,
            executed_quantity=0.0,
            assumed_recommended=False,
            notes=["No broker execution matched this plan. Unmatched executions are never assumed recommended."],
        )

    # A plan existed for this instrument + direction, so a matching fill is "planned".
    if MatchType.OPTION_ASSIGNMENT not in match_types and MatchType.OPTION_EXERCISE not in match_types:
        match_types.add(MatchType.PLANNED)
    match_types.add(MatchType.ADDED if increasing else MatchType.REDUCED)
    if not increasing and plan.direction.value == "exit":
        match_types.add(MatchType.CLOSED)
    if len(matched_txns) > 1:
        match_types.add(MatchType.MULTIPLE_FILLS)
    if plan.proposed_quantity and executed_qty and executed_qty < plan.proposed_quantity:
        match_types.add(MatchType.PARTIAL_FILL)
        notes.append(f"Executed {executed_qty} of planned {plan.proposed_quantity}.")

    return ExecutionMatch(
        match_id=f"em_{uuid4().hex[:12]}",
        trade_plan_id=plan.trade_plan_id,
        account_id=plan.account_id,
        instrument_id=plan.instrument_id,
        symbol=symbol,
        match_types=sorted(match_types, key=lambda m: m.value),
        matched=True,
        transaction_ids=matched_txns,
        planned_quantity=plan.proposed_quantity,
        executed_quantity=executed_qty,
        assumed_recommended=False,
        notes=notes,
    )
