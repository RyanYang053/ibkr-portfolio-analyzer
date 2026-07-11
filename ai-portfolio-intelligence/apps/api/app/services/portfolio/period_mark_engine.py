from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

from app.schemas.domain import Transaction


class IncompletePeriodEffect(RuntimeError):
    pass


@dataclass
class PeriodMarkResult:
    price_effect: Decimal = Decimal("0")
    fx_effect: Decimal = Decimal("0")
    cross_effect: Decimal = Decimal("0")
    trade_timing_effect: Decimal = Decimal("0")
    closing_inventory_effect: Decimal = Decimal("0")
    quantity_bridge: Decimal = Decimal("0")
    exclusions: list[str] = field(default_factory=list)
    complete: bool = True


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


def _matched_signed_quantity(open_qty: Decimal, close_qty: Decimal) -> Decimal:
    if open_qty == 0 or close_qty == 0:
        return Decimal("0")
    if (open_qty > 0) != (close_qty > 0):
        return Decimal("0")
    magnitude = min(abs(open_qty), abs(close_qty))
    return magnitude if open_qty > 0 else -magnitude


def trade_timing_effect(
    txn: Transaction,
    *,
    opening_price: Decimal | None,
    closing_price: Decimal | None,
    trade_fx: Decimal,
    closing_fx: Decimal,
    opening_fx: Decimal | None = None,
    multiplier: Decimal,
) -> Decimal:
    qty = Decimal(str(abs(txn.quantity)))
    trade_price = Decimal(str(txn.price))
    open_fx = opening_fx if opening_fx is not None else trade_fx

    if txn.action == "buy":
        if closing_price is None:
            raise IncompletePeriodEffect("closing mark missing")
        return qty * multiplier * (closing_price * closing_fx - trade_price * trade_fx)

    if txn.action == "sell":
        if opening_price is None:
            raise IncompletePeriodEffect("opening mark missing")
        return qty * multiplier * (trade_price * trade_fx - opening_price * open_fx)

    return Decimal("0")


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


def compute_matched_mark_effects(
    opening: dict,
    closing: dict,
    *,
    period_start: date,
    period_end: date,
    base_currency: str,
    fx_resolver: Callable,
) -> tuple[Decimal, Decimal, Decimal, list[str]]:
    opening_qty = _decimal(opening.get("quantity"))
    closing_qty = _decimal(closing.get("quantity"))
    if opening_qty == 0 and closing_qty == 0:
        return Decimal("0"), Decimal("0"), Decimal("0"), []

    exclusions: list[str] = []
    currency = str(opening.get("currency") or closing.get("currency") or base_currency)
    open_fx = _resolve_fx(currency, base_currency, period_start, fx_resolver)
    close_fx = _resolve_fx(currency, base_currency, period_end, fx_resolver)
    if open_fx is None or close_fx is None:
        exclusions.append(f"fx_unavailable:{opening.get('instrument_key', opening.get('symbol'))}")
        return Decimal("0"), Decimal("0"), Decimal("0"), exclusions

    open_price = _decimal(opening.get("local_price") or opening.get("market_price"))
    close_price = _decimal(closing.get("local_price") or closing.get("market_price"))
    if open_price <= 0 or close_price <= 0:
        exclusions.append("mark_price_missing")
        return Decimal("0"), Decimal("0"), Decimal("0"), exclusions

    multiplier = _decimal(opening.get("multiplier"), Decimal("1")) or Decimal("1")
    matched_qty = _matched_signed_quantity(opening_qty, closing_qty)
    if matched_qty == 0:
        return Decimal("0"), Decimal("0"), Decimal("0"), exclusions

    price_delta = close_price - open_price
    fx_delta = close_fx - open_fx
    price_total = matched_qty * multiplier * price_delta * open_fx
    fx_total = matched_qty * multiplier * open_price * fx_delta
    cross_total = matched_qty * multiplier * price_delta * fx_delta
    return price_total, fx_total, cross_total, exclusions


def compute_period_mark_effects(
    instrument_key: str,
    opening: dict | None,
    closing: dict | None,
    transactions: list[Transaction],
    *,
    period_start: date,
    period_end: date,
    base_currency: str,
    fx_resolver: Callable,
) -> PeriodMarkResult:
    result = PeriodMarkResult()

    if opening is None and closing is None:
        return result

    if opening is not None and closing is not None:
        price, fx, cross, exclusions = compute_matched_mark_effects(
            opening,
            closing,
            period_start=period_start,
            period_end=period_end,
            base_currency=base_currency,
            fx_resolver=fx_resolver,
        )
        result.price_effect += price
        result.fx_effect += fx
        result.cross_effect += cross
        result.exclusions.extend(exclusions)

    instrument_txns = sorted(
        [
            txn
            for txn in transactions
            if txn.action in {"buy", "sell"}
            and period_start < txn.trade_date <= period_end
            and (
                str(txn.con_id or "") == str(opening.get("con_id") if opening else closing.get("con_id") or "")
                or txn.symbol.upper() == str((opening or closing or {}).get("symbol", "")).upper()
            )
        ],
        key=lambda item: (item.event_timestamp, item.source_row_id or "", item.transaction_id or ""),
    )

    multiplier = _decimal(
        (opening or closing or {}).get("multiplier"),
        Decimal("1"),
    ) or Decimal("1")
    open_price = _decimal((opening or {}).get("local_price") or (opening or {}).get("market_price"))
    close_price = _decimal((closing or {}).get("local_price") or (closing or {}).get("market_price"))
    currency = str((opening or closing or {}).get("currency") or base_currency)

    signed_qty = _decimal(opening.get("quantity") if opening else None)
    for txn in instrument_txns:
        trade_fx = _resolve_fx(currency, base_currency, txn.trade_date, fx_resolver)
        close_fx = _resolve_fx(currency, base_currency, period_end, fx_resolver)
        if trade_fx is None or close_fx is None:
            result.exclusions.append(f"fx_unavailable:{instrument_key}")
            result.complete = False
            continue
        try:
            timing = trade_timing_effect(
                txn,
                opening_price=open_price if open_price > 0 else None,
                closing_price=close_price if close_price > 0 else None,
                trade_fx=trade_fx,
                closing_fx=close_fx,
                multiplier=multiplier,
            )
        except IncompletePeriodEffect as exc:
            result.exclusions.append(f"trade_timing_incomplete:{instrument_key}:{exc}")
            result.complete = False
            continue
        result.trade_timing_effect += timing
        qty_delta = Decimal(str(txn.quantity)) if txn.action == "buy" else -Decimal(str(abs(txn.quantity)))
        signed_qty += qty_delta

    closing_qty = _decimal(closing.get("quantity") if closing else None)
    result.quantity_bridge = signed_qty - closing_qty
    if abs(result.quantity_bridge) > Decimal("0.0001"):
        result.exclusions.append(f"quantity_bridge_mismatch:{instrument_key}")
        result.complete = False

    return result
