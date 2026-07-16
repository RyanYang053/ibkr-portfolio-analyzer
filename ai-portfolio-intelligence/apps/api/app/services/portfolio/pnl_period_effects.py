from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from app.schemas.domain import Position
from app.services.portfolio.instrument_identity import instrument_key_from_position, instrument_key_from_row
from app.services.portfolio.period_mark_engine import (
    _matched_signed_quantity,
    compute_period_mark_effects,
)
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.portfolio.transaction_store import get_transactions


@dataclass(frozen=True)
class PeriodEffects:
    price_effect: Decimal | None
    fx_effect: Decimal | None
    price_fx_cross_effect: Decimal | None
    trade_timing_effect: Decimal | None
    income_effect: Decimal | None
    fee_effect: Decimal | None
    withholding_tax_effect: Decimal | None
    corporate_action_effect: Decimal | None
    tax_realized_gain: Decimal | None
    complete: bool
    exclusions: list[str]


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except Exception:
        return None
    if not parsed.is_finite():
        return None
    return parsed


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
        rate = _decimal(quote.rate if hasattr(quote, "rate") else quote)
    except (TypeError, ValueError):
        return None
    if rate is None or rate <= 0:
        return None
    return rate


def _position_to_dict(position: Position | dict) -> dict:
    if isinstance(position, dict):
        return position
    return {
        "instrument_key": instrument_key_from_position(position),
        "con_id": position.con_id,
        "symbol": position.symbol,
        "quantity": float(position.quantity),
        "local_price": float(position.market_price),
        "market_price": float(position.market_price),
        "currency": position.currency,
        "multiplier": float(position.multiplier or 1.0),
    }


def compute_period_effects(
    account_id: str,
    period_start: date,
    period_end: date,
    opening_positions: list[dict],
    closing_positions: list[Position] | list[dict],
    base_currency: str,
    fx_resolver: Callable,
) -> PeriodEffects:
    exclusions: list[str] = []
    complete = True

    opening_by_key = {instrument_key_from_row(row): row for row in opening_positions}
    closing_by_key = {
        instrument_key_from_row(row) if isinstance(row, dict) else instrument_key_from_position(row): _position_to_dict(row)
        for row in closing_positions
    }
    all_keys = sorted(set(opening_by_key) | set(closing_by_key))

    if not opening_by_key:
        exclusions.append("opening_positions_unavailable")
        complete = False

    price_total = Decimal("0")
    fx_total = Decimal("0")
    cross_total = Decimal("0")
    timing_total = Decimal("0")
    price_available = True
    fx_available = True

    transactions = get_transactions(account_id)

    for instrument_key in all_keys:
        opening = opening_by_key.get(instrument_key)
        closing = closing_by_key.get(instrument_key)

        opening_qty = _decimal(opening.get("quantity") if opening else None) or Decimal("0")
        closing_qty = _decimal(closing.get("quantity") if closing else None) or Decimal("0")
        if opening_qty == 0 and closing_qty == 0:
            continue

        if opening is None or closing is None:
            mark_result = compute_period_mark_effects(
                instrument_key,
                opening,
                closing,
                transactions,
                period_start=period_start,
                period_end=period_end,
                base_currency=base_currency,
                fx_resolver=fx_resolver,
            )
            price_total += mark_result.price_effect
            fx_total += mark_result.fx_effect
            cross_total += mark_result.cross_effect
            timing_total += mark_result.trade_timing_effect
            exclusions.extend(mark_result.exclusions)

            if mark_result.complete:
                exclusions.append(f"position_universe_change_reconciled:{instrument_key}")
            else:
                exclusions.append(f"position_universe_change_unreconciled:{instrument_key}")
                complete = False

            continue

        currency = str(opening.get("currency") or closing.get("currency") or base_currency)
        open_fx = _resolve_fx(currency, base_currency, period_start, fx_resolver)
        close_fx = _resolve_fx(currency, base_currency, period_end, fx_resolver)
        if open_fx is None or close_fx is None:
            exclusions.append(f"fx_unavailable:{instrument_key}")
            price_available = False
            fx_available = False
            complete = False
            continue

        open_price = _decimal(opening.get("local_price") or opening.get("market_price"))
        if open_price is None or open_price <= 0:
            exclusions.append(f"opening_market_price_missing:{instrument_key}")
            complete = False
            continue
        close_price = _decimal(closing.get("local_price") or closing.get("market_price"))
        if close_price is None or close_price <= 0:
            exclusions.append(f"closing_market_price_missing:{instrument_key}")
            complete = False
            continue

        multiplier = _decimal(opening.get("multiplier")) or Decimal("1")
        instrument_txns = [
            txn
            for txn in transactions
            if txn.action in {"buy", "sell", "corporate_action"}
            and period_start < txn.trade_date <= period_end
            and (
                str(txn.con_id or "") == str(opening.get("con_id") or closing.get("con_id") or "")
                or txn.symbol.upper() == str(opening.get("symbol", closing.get("symbol", ""))).upper()
            )
        ]
        from app.services.portfolio.signed_inventory_engine import (
            compute_signed_inventory_trade_timing,
            cumulative_split_ratio,
        )

        split_ratio = cumulative_split_ratio(
            instrument_txns,
            period_start=period_start,
            period_end=period_end,
        )
        opening_qty_for_marks = opening_qty * split_ratio
        open_price_for_marks = open_price / split_ratio if split_ratio != 0 else open_price
        matched_qty = _matched_signed_quantity(opening_qty_for_marks, closing_qty)
        if matched_qty != 0:
            price_delta = close_price - open_price_for_marks
            fx_delta = close_fx - open_fx
            price_total += matched_qty * multiplier * price_delta * open_fx
            fx_total += matched_qty * multiplier * open_price_for_marks * fx_delta
            cross_total += matched_qty * multiplier * price_delta * fx_delta

        QUANTITY_BRIDGE_TOLERANCE = Decimal("0.0001")

        timing, calculated_closing_qty, timing_exclusions, timing_complete = (
            compute_signed_inventory_trade_timing(
                opening_qty,
                instrument_txns,
                open_price=open_price,
                close_price=close_price,
                open_fx=open_fx,
                close_fx=close_fx,
                multiplier=multiplier,
                period_start=period_start,
                period_end=period_end,
                currency=currency,
                base_currency=base_currency,
                fx_resolver=fx_resolver,
            )
        )
        timing_total += timing
        exclusions.extend(timing_exclusions)

        quantity_bridge = calculated_closing_qty - closing_qty
        if abs(quantity_bridge) > QUANTITY_BRIDGE_TOLERANCE:
            exclusions.append(
                f"quantity_bridge_mismatch:{instrument_key}:"
                f"calculated={calculated_closing_qty}:"
                f"reported={closing_qty}"
            )
            complete = False

        if not timing_complete:
            complete = False

    tax_lot_report = build_tax_lot_attribution(
        account_id,
        transactions,
        reporting_currency=base_currency,
        period_start=period_start,
        period_end=period_end,
        fx_resolver=fx_resolver,
    )
    tax_realized_gain = (
        _decimal(tax_lot_report.total_realized_gain_loss)
        if tax_lot_report.data_quality.get("status") == "lot_matching_complete"
        else None
    )
    if tax_lot_report.data_quality.get("status") == "unavailable":
        exclusions.append("tax_lot_attribution_withheld")

    income_total = Decimal("0")
    fee_total = Decimal("0")
    withholding_total = Decimal("0")
    corporate_total = Decimal("0")
    for txn in transactions:
        if not (period_start < txn.trade_date <= period_end):
            continue
        amount = _decimal(txn.amount) or _decimal(txn.quantity * txn.price) or Decimal("0")
        if txn.action == "dividend":
            income_total += abs(amount)
        elif txn.action == "interest":
            income_total += amount
        elif txn.action in {"fee", "buy", "sell"}:
            fee_total += abs(_decimal(txn.commission) or Decimal("0"))
        elif txn.action == "withholding_tax":
            withholding_total += abs(amount)
        elif txn.action == "corporate_action":
            corporate_total += amount

    return PeriodEffects(
        price_effect=price_total if price_available and opening_by_key else None,
        fx_effect=fx_total if fx_available and opening_by_key else None,
        price_fx_cross_effect=cross_total if price_available and fx_available and opening_by_key else None,
        trade_timing_effect=timing_total if complete else None,
        income_effect=income_total,
        fee_effect=fee_total,
        withholding_tax_effect=withholding_total,
        corporate_action_effect=corporate_total,
        tax_realized_gain=tax_realized_gain,
        complete=complete and price_available and fx_available,
        exclusions=list(dict.fromkeys(exclusions)),
    )


def compute_period_price_and_realized_effects(
    account_id: str,
    period_start: date,
    period_end: date,
    opening_positions: list[dict],
    closing_positions: list[Position],
    base_currency: str,
    fx_resolver: Callable,
) -> tuple[float | None, float | None, float | None, list[str]]:
    """Backward-compatible wrapper returning combined mark effects."""
    effects = compute_period_effects(
        account_id,
        period_start,
        period_end,
        opening_positions,
        closing_positions,
        base_currency,
        fx_resolver,
    )
    combined = None
    if effects.price_effect is not None and effects.fx_effect is not None and effects.price_fx_cross_effect is not None:
        combined = effects.price_effect + effects.fx_effect + effects.price_fx_cross_effect
    price = float(combined) if combined is not None else None
    return (
        round(price, 2) if price is not None else None,
        float(effects.tax_realized_gain) if effects.tax_realized_gain is not None else None,
        float(effects.fx_effect) if effects.fx_effect is not None else None,
        effects.exclusions,
    )
