from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Callable

from app.schemas.domain import Transaction
from app.services.portfolio.ledger_coverage import external_cash_flow_amount
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot


class ReturnMethod(str, Enum):
    EXACT_TWR = "exact_twr"
    MODIFIED_DIETZ = "modified_dietz"
    SIMPLE_END_FLOW = "simple_end_flow"
    WITHHELD = "withheld"


@dataclass(frozen=True)
class ReturnResult:
    method: ReturnMethod
    return_percent: float | None
    timing_coverage: str
    exclusions: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    methodology: str = ""


def _flow_weight(trade_date: date, interval_start: date, interval_end: date) -> float:
    total_days = max((interval_end - interval_start).days, 1)
    remaining = max((interval_end - trade_date).days, 0)
    return min(max(remaining / total_days, 0.0), 1.0)


def exact_bracketed_nav_available(
    history: list[PortfolioPnLSnapshot],
    flow_transactions: list[Transaction],
) -> bool:
    if not flow_transactions:
        return True
    dated_nav = {item.date: float(item.net_liquidation) for item in history}
    for txn in flow_transactions:
        if txn.trade_timestamp is None and txn.effective_timestamp is None:
            return False
        flow_date = txn.event_timestamp.date().isoformat()
        if flow_date not in dated_nav:
            return False
    return True


def _modified_dietz_return(
    beginning_nav: float,
    ending_nav: float,
    transactions: list[Transaction],
    interval_start: date,
    interval_end: date,
    base_currency: str,
    fx_resolver: Callable,
) -> float | None:
    if beginning_nav <= 0:
        return None
    weighted_flow = 0.0
    total_flow = 0.0
    for txn in transactions:
        if txn.trade_date <= interval_start or txn.trade_date > interval_end:
            continue
        amount = external_cash_flow_amount(txn)
        if amount == 0.0:
            continue
        if txn.currency.upper() == base_currency.upper():
            rate = 1.0
        else:
            quote = fx_resolver(txn.currency, base_currency, txn.trade_date)
            rate = float(quote.rate) if hasattr(quote, "rate") else float(quote)
        converted = amount * rate
        total_flow += converted
        weighted_flow += _flow_weight(txn.trade_date, interval_start, interval_end) * converted
    denominator = beginning_nav + weighted_flow
    if denominator <= 0:
        return None
    interval_return = (ending_nav - beginning_nav - total_flow) / denominator
    return interval_return * 100.0


def compute_period_return(
    history: list[PortfolioPnLSnapshot],
    transactions: list[Transaction],
    *,
    interval_start: date,
    interval_end: date,
    base_currency: str,
    fx_resolver: Callable,
    source_ids: list[str] | None = None,
) -> ReturnResult:
    ordered = sorted(history, key=lambda row: (row.date, row.timestamp))
    start_snap = next((item for item in ordered if item.date == interval_start.isoformat()), None)
    end_snap = next((item for item in ordered if item.date == interval_end.isoformat()), None)
    if start_snap is None or end_snap is None:
        return ReturnResult(
            method=ReturnMethod.WITHHELD,
            return_percent=None,
            timing_coverage="missing_nav_snapshots",
            exclusions=["nav_snapshots_missing"],
            source_ids=source_ids or [],
        )

    beginning_nav = float(start_snap.net_liquidation)
    ending_nav = float(end_snap.net_liquidation)
    flow_txns = [
        txn
        for txn in transactions
        if interval_start < txn.trade_date <= interval_end and external_cash_flow_amount(txn) != 0.0
    ]

    if exact_bracketed_nav_available(ordered, flow_txns):
        total_flow = 0.0
        for txn in flow_txns:
            amount = external_cash_flow_amount(txn)
            if txn.currency.upper() == base_currency.upper():
                rate = 1.0
            else:
                quote = fx_resolver(txn.currency, base_currency, txn.trade_date)
                rate = float(quote.rate) if hasattr(quote, "rate") else float(quote)
            total_flow += amount * rate
        if beginning_nav > 0:
            exact_return = ((ending_nav - beginning_nav - total_flow) / beginning_nav) * 100.0
            return ReturnResult(
                method=ReturnMethod.EXACT_TWR,
                return_percent=round(exact_return, 6),
                timing_coverage="exact_flow_timestamps_with_bracketed_nav",
                source_ids=source_ids or [],
                methodology="Exact TWR with NAV immediately before/after every external flow.",
            )

    has_timestamps = any(
        txn.trade_timestamp is not None or txn.effective_timestamp is not None for txn in flow_txns
    )
    if has_timestamps:
        md_return = _modified_dietz_return(
            beginning_nav,
            ending_nav,
            transactions,
            interval_start,
            interval_end,
            base_currency,
            fx_resolver,
        )
        if md_return is not None:
            return ReturnResult(
                method=ReturnMethod.MODIFIED_DIETZ,
                return_percent=round(md_return, 6),
                timing_coverage="flow_timestamps_without_bracketed_nav",
                exclusions=["bracketed_nav_unavailable"],
                source_ids=source_ids or [],
                methodology="Modified Dietz approximation; exact TWR withheld pending bracketed NAV.",
            )

    total_flow = 0.0
    for txn in flow_txns:
        amount = external_cash_flow_amount(txn)
        if txn.currency.upper() == base_currency.upper():
            rate = 1.0
        else:
            quote = fx_resolver(txn.currency, base_currency, txn.trade_date)
            rate = float(quote.rate) if hasattr(quote, "rate") else float(quote)
        total_flow += amount * rate
    if beginning_nav > 0:
        simple = ((ending_nav - beginning_nav - total_flow) / beginning_nav) * 100.0
        return ReturnResult(
            method=ReturnMethod.SIMPLE_END_FLOW,
            return_percent=round(simple, 6),
            timing_coverage="date_only_flows",
            exclusions=["approximate_end_flow_adjustment"],
            source_ids=source_ids or [],
            methodology="Simple end-flow adjustment; not suitable for Sharpe/beta/alpha.",
        )

    return ReturnResult(
        method=ReturnMethod.WITHHELD,
        return_percent=None,
        timing_coverage="insufficient_data",
        exclusions=["return_withheld"],
        source_ids=source_ids or [],
    )
