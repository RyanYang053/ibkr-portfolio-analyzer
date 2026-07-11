from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Deque, Optional

from app.schemas.domain import Transaction
from app.services.portfolio.corporate_actions import apply_corporate_action_to_lots, parse_corporate_action
from app.services.tax.models import RealizedTaxLot, TaxAttributionReport, TaxLotMethod, TaxLotSnapshot


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
    txn_fx_rate: Optional[float] = None,
) -> tuple[Optional[float], Optional[str]]:
    reporting = reporting_currency.upper()
    native = (currency or reporting).upper()
    if native == reporting:
        return amount, None
    if txn_fx_rate is not None and math.isfinite(float(txn_fx_rate)) and float(txn_fx_rate) > 0:
        return amount * float(txn_fx_rate), "transaction_reported_fx"
    if fx_resolver is None:
        return None, "withheld_mixed_currency"
    try:
        rate = fx_resolver(native, reporting, trade_date)
    except TypeError:
        return None, "withheld_mixed_currency"
    if rate is None or not math.isfinite(float(rate)):
        return None, "withheld_mixed_currency"
    return amount * float(rate), "transaction_date_fx"


def _is_long_term(acquired: date, sold: date) -> bool:
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:
        anniversary = acquired.replace(year=acquired.year + 1, day=28)
    return sold > anniversary


def _is_wash_sale(acquired: date, sold: date, repurchase_dates: list[date], window_days: int = 30) -> bool:
    start = sold - timedelta(days=window_days)
    end = sold + timedelta(days=window_days)
    return any(start <= repurchase <= end for repurchase in repurchase_dates if repurchase != sold)


def build_us_tax_lot_report(
    account_id: str,
    transactions: list[Transaction],
    *,
    reporting_currency: str = "USD",
    period_start: date | None = None,
    period_end: date | None = None,
    lot_method: TaxLotMethod = TaxLotMethod.FIFO,
    fx_resolver: Optional[Callable[..., float]] = None,
    wash_sale_window_days: int = 30,
) -> TaxAttributionReport:
    open_lots: dict[tuple[str, int | None], Deque[_OpenLot]] = defaultdict(deque)
    realized: list[RealizedTaxLot] = []
    repurchase_dates: dict[tuple[str, int | None], list[date]] = defaultdict(list)
    fx_status: str | None = None
    methodology_status = "experimental"

    ordered = sorted(
        (txn for txn in transactions if period_end is None or txn.trade_date <= period_end),
        key=lambda item: (item.trade_date, item.transaction_id or "", item.symbol, item.action),
    )

    for txn in ordered:
        key = _lot_key(txn)
        if txn.action == "corporate_action":
            action = parse_corporate_action(txn)
            if action and open_lots[key]:
                apply_corporate_action_to_lots(open_lots[key], action, txn)
            continue
        if txn.action == "buy":
            notional = txn.price + (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
            converted, status = _convert_amount(
                notional,
                txn.currency,
                reporting_currency,
                txn.trade_date,
                fx_resolver,
                txn.fx_rate,
            )
            if converted is None:
                fx_status = status
                continue
            if status:
                fx_status = status
            repurchase_dates[key].append(txn.trade_date)
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
        emit_realized = period_start is None or txn.trade_date >= period_start
        remaining = abs(txn.quantity)
        proceeds_per_share_native = txn.price - (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
        proceeds_per_share, status = _convert_amount(
            proceeds_per_share_native,
            txn.currency,
            reporting_currency,
            txn.trade_date,
            fx_resolver,
            txn.fx_rate,
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
        wash_sale_blocked = False

        while remaining > 1e-9 and open_lots[key]:
            lot = open_lots[key][0] if lot_method == TaxLotMethod.FIFO else open_lots[key][-1]
            matched = min(remaining, lot.quantity)
            cost = matched * lot.cost_basis_per_share
            proceeds = matched * proceeds_per_share
            gain = proceeds - cost
            holding_days = (txn.trade_date - lot.acquired_date).days
            max_holding_days = max(max_holding_days, holding_days)
            if _is_wash_sale(lot.acquired_date, txn.trade_date, repurchase_dates[key], wash_sale_window_days):
                wash_sale_blocked = True
                gain = 0.0
            if _is_long_term(lot.acquired_date, txn.trade_date):
                long_term += gain
            else:
                short_term += gain
            total_cost += cost
            total_proceeds += proceeds
            matched_qty += matched
            lot.quantity -= matched
            remaining -= matched
            if lot.quantity <= 1e-9:
                if lot_method == TaxLotMethod.FIFO:
                    open_lots[key].popleft()
                else:
                    open_lots[key].pop()

        if emit_realized:
            realized.append(
                RealizedTaxLot(
                    symbol=txn.symbol.upper(),
                    tax_realized_gain_loss=round(total_proceeds - total_cost, 2),
                    short_term_gain_loss=round(short_term, 2),
                    long_term_gain_loss=round(long_term, 2),
                    quantity_sold=round(matched_qty, 6),
                    unmatched_sell_quantity=round(remaining, 6),
                    proceeds=round(total_proceeds, 2),
                    cost_basis=round(total_cost, 2),
                    holding_period_days=max_holding_days,
                    method=lot_method,
                    jurisdiction="US",
                    methodology_status="wash_sale_adjusted" if wash_sale_blocked else methodology_status,
                )
            )

    open_rows = [
        TaxLotSnapshot(
            account_id=account_id,
            symbol=symbol,
            con_id=con_id,
            quantity=round(lot.quantity, 6),
            cost_basis_per_share=round(lot.cost_basis_per_share, 6),
            acquired_date=lot.acquired_date,
            currency=lot.currency,
            jurisdiction="US",
            method=lot_method,
        )
        for (symbol, con_id), lots in open_lots.items()
        for lot in lots
        if lot.quantity > 1e-9
    ]

    unmatched = round(sum(item.unmatched_sell_quantity for item in realized), 6)
    if fx_status == "withheld_mixed_currency":
        status = "incomplete"
        total = None
    elif unmatched > 0:
        status = "incomplete"
        total = None
    elif realized or open_rows:
        status = "lot_matching_complete"
        total = round(sum(item.tax_realized_gain_loss or 0.0 for item in realized), 2)
    else:
        status = "missing"
        total = None

    return TaxAttributionReport(
        account_id=account_id,
        jurisdiction="US",
        method=lot_method,
        methodology_status=methodology_status,
        reporting_currency=reporting_currency,
        open_lots=open_rows,
        realized_lots=realized,
        total_tax_realized_gain_loss=total,
        total_short_term=round(sum(item.short_term_gain_loss or 0.0 for item in realized), 2) if total is not None else None,
        total_long_term=round(sum(item.long_term_gain_loss or 0.0 for item in realized), 2) if total is not None else None,
        unmatched_sell_quantity=max(unmatched, 0.0),
        data_quality={
            "status": status,
            "tax_lot_method": lot_method.value,
            "tax_labeling_jurisdiction": "US",
            "tax_compliance_status": methodology_status,
            **({"fx_conversion": fx_status} if fx_status else {}),
        },
        methodology=(
            "US tax-lot output supports FIFO/specific identification with wash-sale blocking. "
            "Output remains decision support until reconciled to broker tax forms."
        ),
        period_start=period_start,
        period_end=period_end,
    )
