from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from app.schemas.domain import Position, Transaction
from app.services.portfolio.instrument_identity import instrument_key_from_position, instrument_key_from_row
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.portfolio.transaction_store import get_transactions


@dataclass(frozen=True)
class PeriodEffects:
    price_effect: Decimal | None
    fx_effect: Decimal | None
    price_fx_cross_effect: Decimal | None
    realized_lot_effect: Decimal | None
    trade_timing_effect: Decimal | None
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
        rate = _decimal(fx_resolver(currency, base_currency, as_of))
    except (TypeError, ValueError):
        return None
    if rate is None or rate <= 0:
        return None
    return rate


def compute_period_effects(
    account_id: str,
    period_start: date,
    period_end: date,
    opening_positions: list[dict],
    closing_positions: list[Position],
    base_currency: str,
    fx_resolver: Callable,
) -> PeriodEffects:
    exclusions: list[str] = []
    complete = True

    opening_by_key = {instrument_key_from_row(row): row for row in opening_positions}
    closing_by_key = {instrument_key_from_position(position): position for position in closing_positions}
    all_keys = sorted(set(opening_by_key) | set(closing_by_key))

    if not opening_by_key:
        exclusions.append("opening_positions_unavailable")
        complete = False

    price_total = Decimal("0")
    fx_total = Decimal("0")
    cross_total = Decimal("0")
    price_available = True
    fx_available = True

    for instrument_key in all_keys:
        opening = opening_by_key.get(instrument_key)
        closing = closing_by_key.get(instrument_key)

        opening_qty = _decimal(opening.get("quantity") if opening else None) or Decimal("0")
        closing_qty = _decimal(closing.quantity if closing else None) or Decimal("0")
        if opening_qty <= 0 and closing_qty <= 0:
            continue

        if opening is None or closing is None:
            exclusions.append(f"position_universe_change:{instrument_key}")
            continue

        currency = str(opening.get("currency") or closing.currency or base_currency)
        open_fx = _resolve_fx(currency, base_currency, period_start, fx_resolver)
        close_fx = _resolve_fx(currency, base_currency, period_end, fx_resolver)
        if open_fx is None or close_fx is None:
            exclusions.append(f"fx_unavailable:{instrument_key}")
            price_available = False
            fx_available = False
            complete = False
            continue

        open_price = _decimal(opening.get("market_price"))
        if open_price is None or open_price <= 0:
            exclusions.append(f"opening_market_price_missing:{instrument_key}")
            complete = False
            continue
        close_price = _decimal(closing.market_price)
        if close_price is None or close_price <= 0:
            exclusions.append(f"closing_market_price_missing:{instrument_key}")
            complete = False
            continue

        matched_qty = min(opening_qty, closing_qty)
        if matched_qty <= 0:
            continue

        price_delta = close_price - open_price
        fx_delta = close_fx - open_fx
        price_total += matched_qty * price_delta * open_fx
        fx_total += matched_qty * open_price * fx_delta
        cross_total += matched_qty * price_delta * fx_delta

    transactions = get_transactions(account_id)
    lot_report = build_tax_lot_attribution(
        account_id,
        transactions,
        reporting_currency=base_currency,
        period_start=period_start,
        period_end=period_end,
        fx_resolver=fx_resolver,
    )
    realized_lot = _decimal(lot_report.total_realized_gain_loss)
    if lot_report.data_quality.get("status") == "unavailable":
        exclusions.append("realized_lot_attribution_withheld")
        complete = False

    return PeriodEffects(
        price_effect=price_total if price_available and opening_by_key else None,
        fx_effect=fx_total if fx_available and opening_by_key else None,
        price_fx_cross_effect=cross_total if price_available and fx_available and opening_by_key else None,
        realized_lot_effect=realized_lot,
        trade_timing_effect=None,
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
    """Backward-compatible wrapper returning combined mark effects and realized lots."""
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
    realized = float(effects.realized_lot_effect) if effects.realized_lot_effect is not None else None
    price = float(combined) if combined is not None else None
    return (
        round(price, 2) if price is not None else None,
        round(realized, 2) if realized is not None else None,
        float(effects.fx_effect) if effects.fx_effect is not None else None,
        effects.exclusions,
    )
