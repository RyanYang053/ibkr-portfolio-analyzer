from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Deque

from app.schemas.domain import RealizedLotAttribution, TaxLot, TaxLotAttributionReport, Transaction

LONG_TERM_DAYS = 365


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
) -> TaxLotAttributionReport:
    open_lots: dict[tuple[str, int | None], Deque[_OpenLot]] = defaultdict(deque)
    realized_rows: list[RealizedLotAttribution] = []

    ordered = sorted(transactions, key=lambda item: (item.trade_date, item.symbol, item.action))
    for txn in ordered:
        key = _lot_key(txn)
        if txn.action == "buy":
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
        if txn.action != "sell" or not open_lots[key]:
            continue

        remaining = abs(txn.quantity)
        proceeds_per_share = txn.price - (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
        total_proceeds = 0.0
        total_cost = 0.0
        short_term = 0.0
        long_term = 0.0
        while remaining > 1e-9 and open_lots[key]:
            lot = open_lots[key][0]
            matched = min(remaining, lot.quantity)
            cost = matched * lot.cost_basis_per_share
            proceeds = matched * proceeds_per_share
            gain = proceeds - cost
            holding_days = (txn.trade_date - lot.acquired_date).days
            if holding_days >= LONG_TERM_DAYS:
                long_term += gain
            else:
                short_term += gain
            total_cost += cost
            total_proceeds += proceeds
            lot.quantity -= matched
            remaining -= matched
            if lot.quantity <= 1e-9:
                open_lots[key].popleft()

        realized_rows.append(
            RealizedLotAttribution(
                symbol=txn.symbol.upper(),
                realized_gain_loss=round(total_proceeds - total_cost, 2),
                short_term_gain_loss=round(short_term, 2),
                long_term_gain_loss=round(long_term, 2),
                quantity_sold=round(abs(txn.quantity) - remaining, 6),
                proceeds=round(total_proceeds, 2),
                cost_basis=round(total_cost, 2),
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

    total_realized = round(sum(row.realized_gain_loss for row in realized_rows), 2)
    total_short = round(sum(row.short_term_gain_loss for row in realized_rows), 2)
    total_long = round(sum(row.long_term_gain_loss for row in realized_rows), 2)
    status = "sufficient" if realized_rows or open_rows else "missing"

    return TaxLotAttributionReport(
        account_id=account_id,
        lots_open=open_rows,
        realized_by_symbol=realized_rows,
        total_realized_gain_loss=total_realized,
        total_short_term=total_short,
        total_long_term=total_long,
        data_quality={
            "tax_lot_method": "fifo",
            "transaction_count": str(len(transactions)),
            "status": status,
        },
        methodology=(
            "Realized gains and losses are computed using FIFO tax lots from buy/sell transactions. "
            "Long-term classification uses a 365-day holding period."
        ),
    )


def realized_gain_by_symbol(transactions: list[Transaction], account_id: str) -> dict[str, float]:
    report = build_tax_lot_attribution(account_id, transactions)
    grouped: dict[str, float] = defaultdict(float)
    for row in report.realized_by_symbol:
        grouped[row.symbol] += row.realized_gain_loss
    return {symbol: round(value, 2) for symbol, value in grouped.items()}
