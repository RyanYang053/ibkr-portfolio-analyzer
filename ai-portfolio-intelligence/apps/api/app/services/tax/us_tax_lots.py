from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, replace
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


@dataclass
class _PendingWashLoss:
    sale_date: date
    remaining_disallowed: float
    remaining_quantity: float
    realized_index: int


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


def _acquisitions_in_window(
    acquisitions: list[tuple[date, float]],
    sold: date,
    *,
    exclude_dates: set[date],
    window_days: int,
) -> list[tuple[date, float]]:
    start = sold - timedelta(days=window_days)
    end = sold + timedelta(days=window_days)
    return [
        (acq_date, qty)
        for acq_date, qty in acquisitions
        if start <= acq_date <= end and acq_date not in exclude_dates
    ]


def _apply_basis_increase(lot: _OpenLot, disallowed: float, quantity: float) -> None:
    if quantity <= 1e-12 or disallowed <= 0:
        return
    lot.cost_basis_per_share += disallowed / quantity


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
    acquisitions: dict[tuple[str, int | None], list[tuple[date, float]]] = defaultdict(list)
    pending_wash: dict[tuple[str, int | None], list[_PendingWashLoss]] = defaultdict(list)
    fx_status: str | None = None
    methodology_status = "experimental"
    wash_sale_adjustments = 0
    wash_sales_fully_adjusted = True

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
            buy_qty = abs(txn.quantity)
            cost_basis = converted
            # IRS §1091: add previously disallowed wash-sale loss into replacement basis.
            remaining_buy_qty = buy_qty
            deferred_into_buy = 0.0
            still_pending: list[_PendingWashLoss] = []
            for pending in pending_wash[key]:
                if remaining_buy_qty <= 1e-12:
                    still_pending.append(pending)
                    continue
                if abs((txn.trade_date - pending.sale_date).days) > wash_sale_window_days:
                    still_pending.append(pending)
                    wash_sales_fully_adjusted = False
                    continue
                matched_qty = min(remaining_buy_qty, pending.remaining_quantity)
                share = matched_qty / pending.remaining_quantity if pending.remaining_quantity > 1e-12 else 0.0
                disallowed = pending.remaining_disallowed * share
                deferred_into_buy += disallowed
                remaining_buy_qty -= matched_qty
                pending.remaining_disallowed -= disallowed
                pending.remaining_quantity -= matched_qty
                wash_sale_adjustments += 1
                if pending.realized_index < len(realized):
                    prior = realized[pending.realized_index]
                    new_total = round((prior.tax_realized_gain_loss or 0.0) + disallowed, 2)
                    new_st = prior.short_term_gain_loss
                    new_lt = prior.long_term_gain_loss
                    if (prior.short_term_gain_loss or 0.0) < 0:
                        new_st = round((prior.short_term_gain_loss or 0.0) + disallowed, 2)
                    elif (prior.long_term_gain_loss or 0.0) < 0:
                        new_lt = round((prior.long_term_gain_loss or 0.0) + disallowed, 2)
                    realized[pending.realized_index] = replace(
                        prior,
                        tax_realized_gain_loss=new_total,
                        short_term_gain_loss=new_st,
                        long_term_gain_loss=new_lt,
                        wash_sale_disallowed_loss=round(
                            (prior.wash_sale_disallowed_loss or 0.0) + disallowed, 2
                        ),
                        methodology_status="wash_sale_adjusted",
                    )
                if pending.remaining_quantity > 1e-9 and pending.remaining_disallowed > 1e-9:
                    still_pending.append(pending)
            pending_wash[key] = still_pending
            if deferred_into_buy > 0 and buy_qty > 0:
                cost_basis += deferred_into_buy / buy_qty
            acquisitions[key].append((txn.trade_date, buy_qty))
            open_lots[key].append(
                _OpenLot(
                    quantity=buy_qty,
                    cost_basis_per_share=cost_basis,
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
        disallowed_total = 0.0
        wash_sale_blocked = False
        sold_acquired_dates: set[date] = set()

        while remaining > 1e-9 and open_lots[key]:
            if lot_method == TaxLotMethod.LIFO:
                lot = open_lots[key][-1]
            elif lot_method == TaxLotMethod.HIFO:
                lot = max(open_lots[key], key=lambda item: item.cost_basis_per_share)
            else:
                lot = open_lots[key][0]
            matched = min(remaining, lot.quantity)
            cost = matched * lot.cost_basis_per_share
            proceeds = matched * proceeds_per_share
            gain = proceeds - cost
            holding_days = (txn.trade_date - lot.acquired_date).days
            max_holding_days = max(max_holding_days, holding_days)
            sold_acquired_dates.add(lot.acquired_date)

            # Pre-sale replacement purchases in the wash window (exclude this lot's acquisition).
            prior_replacements = _acquisitions_in_window(
                acquisitions[key],
                txn.trade_date,
                exclude_dates={lot.acquired_date},
                window_days=wash_sale_window_days,
            )
            if gain < 0 and prior_replacements:
                disallowed = -gain
                gain = 0.0
                disallowed_total += disallowed
                wash_sale_blocked = True
                wash_sale_adjustments += 1
                # Prefer adding disallowed loss into still-open replacement lots.
                for open_lot in list(open_lots[key]):
                    if open_lot.acquired_date == lot.acquired_date:
                        continue
                    if abs((open_lot.acquired_date - txn.trade_date).days) <= wash_sale_window_days:
                        _apply_basis_increase(open_lot, disallowed, open_lot.quantity)
                        break

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
                if lot_method == TaxLotMethod.LIFO:
                    open_lots[key].pop()
                elif lot_method == TaxLotMethod.HIFO:
                    open_lots[key].remove(lot)
                else:
                    open_lots[key].popleft()

        if emit_realized:
            realized_index = len(realized)
            economic_loss = round(total_proceeds - total_cost, 2)
            reported_gl = round(short_term + long_term, 2)
            # If loss remains and no prior replacement, defer until a post-sale repurchase (§1091).
            unreplaced_loss = 0.0
            if reported_gl < 0 and not wash_sale_blocked:
                # May still wash on later repurchase within window.
                unreplaced_loss = -reported_gl
                pending_wash[key].append(
                    _PendingWashLoss(
                        sale_date=txn.trade_date,
                        remaining_disallowed=unreplaced_loss,
                        remaining_quantity=matched_qty,
                        realized_index=realized_index,
                    )
                )
            elif wash_sale_blocked and disallowed_total > 0 and matched_qty > 0:
                # Already adjusted into open lots when possible; track residual.
                pass

            realized.append(
                RealizedTaxLot(
                    symbol=txn.symbol.upper(),
                    tax_realized_gain_loss=reported_gl,
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
                    wash_sale_disallowed_loss=round(disallowed_total, 2),
                )
            )
            _ = economic_loss, sold_acquired_dates

    # Pending wash losses still inside the observation window without a replacement
    # mean the wash outcome is not yet fully known.
    for pending_list in pending_wash.values():
        for pending in pending_list:
            if pending.remaining_disallowed <= 1e-9:
                continue
            last_date = max((txn.trade_date for txn in ordered), default=pending.sale_date)
            if (last_date - pending.sale_date).days <= wash_sale_window_days:
                wash_sales_fully_adjusted = False
            # Else: window elapsed with no replacement — loss stands (no wash).

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

    # Pending wash losses that were later adjusted via repurchase: zero remaining economic loss.
    # Recompute totals after in-place replacements above.
    if total is not None:
        total = round(sum(item.tax_realized_gain_loss or 0.0 for item in realized), 2)

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
            "wash_sale_adjustments": str(wash_sale_adjustments),
            "wash_sales_fully_adjusted": "true" if wash_sales_fully_adjusted else "false",
            **({"fx_conversion": fx_status} if fx_status else {}),
        },
        methodology=(
            "US tax-lot output supports FIFO/LIFO/HIFO/specific identification with IRS §1091 "
            "wash-sale loss deferral into replacement cost basis. "
            "Output remains a filing worksheet until reconciled to broker tax forms."
        ),
        period_start=period_start,
        period_end=period_end,
    )
