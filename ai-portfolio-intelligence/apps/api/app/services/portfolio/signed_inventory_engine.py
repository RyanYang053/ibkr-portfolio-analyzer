from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from app.schemas.domain import Transaction
from app.services.portfolio.corporate_actions import parse_corporate_action


def _decimal(value: object, default: Decimal | None = None) -> Decimal:
    if value is None:
        return default if default is not None else Decimal("0")
    try:
        parsed = Decimal(str(value))
    except Exception:
        return default if default is not None else Decimal("0")
    if not parsed.is_finite():
        return default if default is not None else Decimal("0")
    return parsed


def cumulative_split_ratio(
    transactions: list[Transaction],
    *,
    period_start: date,
    period_end: date,
) -> Decimal:
    """Product of explicit split ratios in (period_start, period_end]."""
    ratio = Decimal("1")
    for txn in sorted(
        (
            item
            for item in transactions
            if item.action == "corporate_action" and period_start < item.trade_date <= period_end
        ),
        key=lambda item: (item.event_timestamp, item.source_row_id or "", item.transaction_id or ""),
    ):
        action = parse_corporate_action(txn)
        if action is None or action.action_type != "split":
            continue
        split_ratio = Decimal(str(action.ratio))
        if split_ratio <= 0:
            continue
        ratio *= split_ratio
    return ratio


def _resolve_fx(
    currency: str,
    base_currency: str,
    as_of: date,
    fx_resolver: Callable,
) -> Decimal | None:
    if currency.upper() == base_currency.upper():
        return Decimal("1")
    try:
        quote = fx_resolver(currency, base_currency, as_of)
        if isinstance(quote, (float, int)):
            rate = Decimal(str(quote))
        else:
            rate = Decimal(str(quote.rate))
    except (TypeError, ValueError):
        return None
    if rate <= 0:
        return None
    return rate


def compute_signed_inventory_trade_timing(
    opening_qty: Decimal,
    transactions: list[Transaction],
    *,
    open_price: Decimal,
    close_price: Decimal,
    open_fx: Decimal,
    close_fx: Decimal,
    multiplier: Decimal,
    period_start: date,
    period_end: date,
    currency: str,
    base_currency: str,
    fx_resolver: Callable,
) -> tuple[Decimal, Decimal, list[str], bool]:
    """Process signed inventory in event order for buy/sell timing effects."""
    inventory = opening_qty
    total = Decimal("0")
    exclusions: list[str] = []
    complete = True
    # Normalize opening marks onto the closing share basis as splits are applied.
    mark_open_price = open_price

    instrument_txns = sorted(
        [
            txn
            for txn in transactions
            if txn.action in {"buy", "sell", "corporate_action"}
            and period_start < txn.trade_date <= period_end
        ],
        key=lambda item: (item.event_timestamp, item.source_row_id or "", item.transaction_id or ""),
    )

    for txn in instrument_txns:
        if txn.action == "corporate_action":
            action = parse_corporate_action(txn)

            if action is None:
                exclusions.append(
                    f"unsupported_corporate_action:{txn.symbol}:"
                    f"{txn.transaction_id or txn.source_row_id or 'unknown'}"
                )
                complete = False
                continue

            if action.action_type == "split":
                ratio = Decimal(str(action.ratio))
                if ratio <= 0:
                    exclusions.append(
                        f"unsupported_corporate_action:{txn.symbol}:"
                        f"{txn.transaction_id or txn.source_row_id or 'unknown'}"
                    )
                    complete = False
                    continue
                inventory *= ratio
                mark_open_price = mark_open_price / ratio
                exclusions.append(
                    f"corporate_action_price_normalized:{txn.symbol}:ratio={ratio}"
                )
                continue

            exclusions.append(
                f"unsupported_corporate_action_type:{txn.symbol}:{action.action_type}"
            )
            complete = False
            continue

        trade_qty = _decimal(abs(txn.quantity))
        if trade_qty <= 0:
            continue
        trade_fx = _resolve_fx(currency, base_currency, txn.trade_date, fx_resolver)
        if trade_fx is None:
            exclusions.append(f"fx_unavailable:{txn.symbol}")
            complete = False
            continue

        trade_price = _decimal(txn.price)
        if trade_price <= 0:
            exclusions.append(f"trade_price_missing:{txn.symbol}")
            complete = False
            continue

        if txn.action == "buy":
            if inventory >= 0:
                if close_price <= 0:
                    exclusions.append(f"closing_mark_missing:{txn.symbol}")
                    complete = False
                else:
                    total += trade_qty * multiplier * (close_price * close_fx - trade_price * trade_fx)
                inventory += trade_qty
                continue

            cover_qty = min(trade_qty, abs(inventory))
            if cover_qty > 0:
                if mark_open_price <= 0:
                    exclusions.append(f"opening_mark_missing:{txn.symbol}")
                    complete = False
                else:
                    total += cover_qty * multiplier * (mark_open_price * open_fx - trade_price * trade_fx)
                inventory += cover_qty

            open_long_qty = trade_qty - cover_qty
            if open_long_qty > 0:
                if close_price <= 0:
                    exclusions.append(f"closing_mark_missing:{txn.symbol}")
                    complete = False
                else:
                    total += open_long_qty * multiplier * (close_price * close_fx - trade_price * trade_fx)
                inventory += open_long_qty
            continue

        if inventory <= 0:
            if close_price <= 0:
                exclusions.append(f"closing_mark_missing:{txn.symbol}")
                complete = False
            else:
                total += trade_qty * multiplier * (trade_price * trade_fx - close_price * close_fx)
            inventory -= trade_qty
            continue

        close_qty = min(trade_qty, inventory)
        if close_qty > 0:
            if mark_open_price <= 0:
                exclusions.append(f"opening_mark_missing:{txn.symbol}")
                complete = False
            else:
                total += close_qty * multiplier * (trade_price * trade_fx - mark_open_price * open_fx)
            inventory -= close_qty

        open_short_qty = trade_qty - close_qty
        if open_short_qty > 0:
            if close_price <= 0:
                exclusions.append(f"closing_mark_missing:{txn.symbol}")
                complete = False
            else:
                total += open_short_qty * multiplier * (trade_price * trade_fx - close_price * close_fx)
            inventory -= open_short_qty

    return total, inventory, exclusions, complete
