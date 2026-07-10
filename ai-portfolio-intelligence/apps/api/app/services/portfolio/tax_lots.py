from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Callable, Deque, Literal, Optional

from app.schemas.domain import RealizedLotAttribution, TaxLot, TaxLotAttributionReport, Transaction

EXECUTION_ACTIONS = frozenset({"buy", "sell"})
CORPORATE_ACTIONS = frozenset({"corporate_action"})


@dataclass
class _OpenLot:
    quantity: float
    cost_basis_per_share: float
    acquired_date: date
    currency: str
    con_id: int | None


def _lot_key(txn: Transaction) -> tuple[str, int | None]:
    return (txn.symbol.upper(), txn.con_id)


def _convert_amount(
    amount: float,
    currency: str,
    reporting_currency: str,
    trade_date: date,
    fx_resolver: Optional[Callable[..., float]],
) -> tuple[Optional[float], Optional[str]]:
    reporting = reporting_currency.upper()
    native = (currency or reporting).upper()
    if native == reporting:
        return amount, None
    if fx_resolver is None:
        return None, "withheld_mixed_currency"
    try:
        rate = fx_resolver(native, reporting, trade_date)
    except TypeError:
        return None, "withheld_mixed_currency"
    if rate is None or not math.isfinite(float(rate)):
        return None, "withheld_mixed_currency"
    return amount * float(rate), "transaction_date_fx"


def build_tax_lot_attribution(
    account_id: str,
    transactions: list[Transaction],
    reporting_currency: str = "USD",
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    tax_labeling_jurisdiction: Literal["US", "CA", "OTHER"] = "OTHER",
    fx_resolver: Optional[Callable[..., float]] = None,
) -> TaxLotAttributionReport:
    open_lots: dict[tuple[str, int | None], Deque[_OpenLot]] = defaultdict(deque)
    realized_rows: list[RealizedLotAttribution] = []
    execution_rows = [txn for txn in transactions if txn.action in EXECUTION_ACTIONS]
    corporate_rows = [txn for txn in transactions if txn.action in CORPORATE_ACTIONS]
    buys_before_period = 0
    fx_status: Optional[str] = None

    ordered = sorted(transactions, key=lambda item: (item.trade_date, item.symbol, item.action))
    if period_start:
        ordered = [txn for txn in ordered if txn.trade_date <= (period_end or date.today())]

    for txn in ordered:
        key = _lot_key(txn)
        if txn.action == "buy":
            notional = txn.price + (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
            converted, status = _convert_amount(notional, txn.currency, reporting_currency, txn.trade_date, fx_resolver)
            if converted is None:
                fx_status = status
                continue
            if status:
                fx_status = status
            if period_start and txn.trade_date < period_start:
                buys_before_period += 1
            open_lots[key].append(
                _OpenLot(
                    quantity=abs(txn.quantity),
                    cost_basis_per_share=converted,
                    acquired_date=txn.trade_date,
                    currency=reporting_currency.upper(),
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
        proceeds_per_share_native = txn.price - (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
        proceeds_per_share, status = _convert_amount(
            proceeds_per_share_native,
            txn.currency,
            reporting_currency,
            txn.trade_date,
            fx_resolver,
        )
        if proceeds_per_share is None:
            fx_status = status
            continue
        if status:
            fx_status = status

        total_proceeds = 0.0
        total_cost = 0.0
        short_term = 0.0
        long_term = 0.0
        matched_qty = 0.0
        max_holding_days = 0

        while remaining > 1e-9 and open_lots[key]:
            lot = open_lots[key][0]
            matched = min(remaining, lot.quantity)
            cost = matched * lot.cost_basis_per_share
            proceeds = matched * proceeds_per_share
            gain = proceeds - cost
            holding_days = (txn.trade_date - lot.acquired_date).days
            max_holding_days = max(max_holding_days, holding_days)
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
                holding_period_days=max_holding_days,
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
    incomplete_opening_lots = has_unmatched
    if period_start:
        incomplete_opening_lots = incomplete_opening_lots or (
            bool(execution_rows)
            and buys_before_period == 0
            and any(txn.action == "sell" for txn in execution_rows)
        )

    txn_currencies = {txn.currency.upper() for txn in execution_rows if txn.currency}
    mixed_currency = any(currency != reporting_currency.upper() for currency in txn_currencies)

    if corporate_rows:
        status = "incomplete"
        corp_note = "corporate_actions_unsupported"
    elif fx_status == "withheld_mixed_currency" or (mixed_currency and fx_resolver is None):
        status = "incomplete"
        corp_note = None
    elif incomplete_opening_lots or has_unmatched:
        status = "incomplete"
        corp_note = None
    elif realized_rows or open_rows:
        status = "sufficient"
        corp_note = None
    else:
        status = "missing"
        corp_note = None

    total_realized = round(sum(row.realized_gain_loss for row in realized_rows), 2) if status == "sufficient" else 0.0
    total_short = round(sum(row.short_term_gain_loss or 0.0 for row in realized_rows), 2) if status == "sufficient" else 0.0
    total_long = round(sum(row.long_term_gain_loss or 0.0 for row in realized_rows), 2) if status == "sufficient" else 0.0

    methodology = (
        "Realized gains and losses are computed using FIFO tax lots from buy/sell executions only. "
        "Tax-lot output is separate from portfolio performance attribution and is withheld when opening "
        "lots, execution history, or transaction-date FX conversion are incomplete."
    )
    if tax_labeling_jurisdiction != "US":
        methodology += " US short-term/long-term tax labels are omitted for non-US reporting."
    if fx_status == "withheld_mixed_currency":
        methodology += (
            f" Mixed-currency execution history requires transaction-date FX conversion into "
            f"{reporting_currency.upper()}; totals are withheld until conversion is available."
        )
    if corporate_rows:
        methodology += " Corporate actions are not yet applied to tax lots; output is withheld."

    data_quality = {
        "tax_lot_method": "fifo",
        "transaction_count": str(len(transactions)),
        "execution_count": str(len(execution_rows)),
        "status": status,
        "tax_labeling_jurisdiction": tax_labeling_jurisdiction,
    }
    if fx_status:
        data_quality["fx_conversion"] = fx_status
    elif mixed_currency and fx_resolver is not None:
        data_quality["fx_conversion"] = "transaction_date_fx"
    if corp_note:
        data_quality["corporate_actions"] = corp_note

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
        data_quality=data_quality,
        methodology=methodology,
    )


def realized_gain_by_symbol(
    transactions: list[Transaction],
    account_id: str,
    reporting_currency: str = "USD",
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    fx_resolver: Optional[Callable[..., float]] = None,
) -> dict[str, float]:
    report = build_tax_lot_attribution(
        account_id,
        transactions,
        reporting_currency=reporting_currency,
        period_start=period_start,
        period_end=period_end,
        fx_resolver=fx_resolver,
    )
    if report.data_quality.get("status") != "sufficient":
        return {}
    grouped: dict[str, float] = defaultdict(float)
    for row in report.realized_by_symbol:
        grouped[row.symbol] += row.realized_gain_loss
    return {symbol: round(value, 2) for symbol, value in grouped.items()}
