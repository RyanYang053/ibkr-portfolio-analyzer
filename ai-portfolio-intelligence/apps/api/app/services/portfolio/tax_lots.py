from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Deque, Literal, Optional

from app.schemas.domain import RealizedLotAttribution, TaxLot, TaxLotAttributionReport, Transaction

EXECUTION_ACTIONS = frozenset({"buy", "sell"})


@dataclass
class _OpenLot:
    quantity: float
    cost_basis_per_share: float
    acquired_date: date
    currency: str
    con_id: int | None


def _lot_key(txn: Transaction) -> tuple[str, int | None]:
    return (txn.symbol.upper(), txn.con_id)


def build_tax_lot_attribution(
    account_id: str,
    transactions: list[Transaction],
    reporting_currency: str = "USD",
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    tax_labeling_jurisdiction: Literal["US", "CA", "OTHER"] = "OTHER",
) -> TaxLotAttributionReport:
    open_lots: dict[tuple[str, int | None], Deque[_OpenLot]] = defaultdict(deque)
    realized_rows: list[RealizedLotAttribution] = []
    execution_rows = [txn for txn in transactions if txn.action in EXECUTION_ACTIONS]
    buys_before_period = 0

    ordered = sorted(transactions, key=lambda item: (item.trade_date, item.symbol, item.action))
    if period_start:
        ordered = [txn for txn in ordered if txn.trade_date <= (period_end or date.today())]

    for txn in ordered:
        key = _lot_key(txn)
        if txn.action == "buy":
            if period_start and txn.trade_date < period_start:
                buys_before_period += 1
            open_lots[key].append(
                _OpenLot(
                    quantity=abs(txn.quantity),
                    cost_basis_per_share=txn.price + (txn.commission / abs(txn.quantity) if txn.quantity else 0.0),
                    acquired_date=txn.trade_date,
                    currency=txn.currency,
                    con_id=txn.con_id,
                )
            )
            continue
        if txn.action != "sell":
            continue
        if period_start and txn.trade_date < period_start:
            continue
        if period_end and txn.trade_date > period_end:
            continue

        remaining = abs(txn.quantity)
        proceeds_per_share = txn.price - (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
        total_proceeds = 0.0
        total_cost = 0.0
        short_term = 0.0
        long_term = 0.0
        matched_qty = 0.0

        while remaining > 1e-9 and open_lots[key]:
            lot = open_lots[key][0]
            matched = min(remaining, lot.quantity)
            cost = matched * lot.cost_basis_per_share
            proceeds = matched * proceeds_per_share
            gain = proceeds - cost
            holding_days = (txn.trade_date - lot.acquired_date).days
            if tax_labeling_jurisdiction == "US":
                if holding_days >= 365:
                    long_term += gain
                else:
                    short_term += gain
            total_cost += cost
            total_proceeds += proceeds
            matched_qty += matched
            lot.quantity -= matched
            remaining -= matched
            if lot.quantity <= 1e-9:
                open_lots[key].popleft()

        realized_rows.append(
            RealizedLotAttribution(
                symbol=txn.symbol.upper(),
                realized_gain_loss=round(total_proceeds - total_cost, 2),
                short_term_gain_loss=round(short_term, 2) if tax_labeling_jurisdiction == "US" else None,
                long_term_gain_loss=round(long_term, 2) if tax_labeling_jurisdiction == "US" else None,
                quantity_sold=round(matched_qty, 6),
                unmatched_sell_quantity=round(remaining, 6),
                proceeds=round(total_proceeds, 2),
                cost_basis=round(total_cost, 2),
                holding_period_days=max((txn.trade_date - ordered[0].trade_date).days, 0) if ordered else 0,
            )
        )

    open_rows: list[TaxLot] = []
    for (symbol, con_id), lots in open_lots.items():
        for lot in lots:
            if lot.quantity <= 1e-9:
                continue
            open_rows.append(
                TaxLot(
                    account_id=account_id,
                    symbol=symbol,
                    con_id=con_id,
                    quantity=round(lot.quantity, 6),
                    cost_basis_per_share=round(lot.cost_basis_per_share, 6),
                    acquired_date=lot.acquired_date,
                    currency=lot.currency,
                )
            )

    unmatched_total = round(sum(row.unmatched_sell_quantity for row in realized_rows), 6)
    has_unmatched = unmatched_total > 0
    incomplete_opening_lots = has_unmatched or (bool(execution_rows) and buys_before_period == 0 and any(txn.action == "sell" for txn in execution_rows))

    if incomplete_opening_lots or has_unmatched:
        status = "incomplete"
    elif realized_rows or open_rows:
        status = "sufficient"
    else:
        status = "missing"

    total_realized = round(sum(row.realized_gain_loss for row in realized_rows), 2)
    total_short = round(sum(row.short_term_gain_loss or 0.0 for row in realized_rows), 2)
    total_long = round(sum(row.long_term_gain_loss or 0.0 for row in realized_rows), 2)

    methodology = (
        "Realized gains and losses are computed using FIFO tax lots from buy/sell executions only. "
        "Tax-lot output is separate from portfolio performance attribution and is withheld when opening "
        "lots or execution history are incomplete."
    )
    if tax_labeling_jurisdiction != "US":
        methodology += " US short-term/long-term tax labels are omitted for non-US reporting."

    return TaxLotAttributionReport(
        account_id=account_id,
        lots_open=open_rows,
        realized_by_symbol=realized_rows,
        total_realized_gain_loss=total_realized,
        total_short_term=total_short if tax_labeling_jurisdiction == "US" else 0.0,
        total_long_term=total_long if tax_labeling_jurisdiction == "US" else 0.0,
        reporting_currency=reporting_currency,
        period_start=period_start,
        period_end=period_end,
        unmatched_sell_quantity=unmatched_total,
        data_quality={
            "tax_lot_method": "fifo",
            "transaction_count": str(len(transactions)),
            "execution_count": str(len(execution_rows)),
            "status": status,
            "tax_labeling_jurisdiction": tax_labeling_jurisdiction,
        },
        methodology=methodology,
    )


def realized_gain_by_symbol(
    transactions: list[Transaction],
    account_id: str,
    reporting_currency: str = "USD",
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> dict[str, float]:
    report = build_tax_lot_attribution(
        account_id,
        transactions,
        reporting_currency=reporting_currency,
        period_start=period_start,
        period_end=period_end,
    )
    if report.data_quality.get("status") != "sufficient":
        return {}
    grouped: dict[str, float] = defaultdict(float)
    for row in report.realized_by_symbol:
        grouped[row.symbol] += row.realized_gain_loss
    return {symbol: round(value, 2) for symbol, value in grouped.items()}
