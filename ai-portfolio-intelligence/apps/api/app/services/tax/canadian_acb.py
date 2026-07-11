from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional

from app.schemas.domain import Transaction
from app.services.portfolio.corporate_actions import parse_corporate_action
from app.services.tax.models import RealizedTaxLot, TaxAttributionReport, TaxLotMethod, TaxLotSnapshot

SUPERFICIAL_LOSS_WINDOW_DAYS = 30


@dataclass
class _AcbPool:
    quantity: float = 0.0
    total_cost_cad: float = 0.0


@dataclass
class _SuperficialLossEvent:
    trade_date: date
    symbol: str
    con_id: int | None
    loss_amount: float
    quantity: float
    resolved: bool = False
    realized_index: int | None = None


def superficial_loss_blocked_symbols(report: TaxAttributionReport) -> tuple[str, ...]:
    raw = report.data_quality.get("superficial_loss_blocked_symbols", "")
    if not raw:
        return ()
    return tuple(part.strip().upper() for part in raw.split(",") if part.strip())


def _convert_to_cad(
    amount: float,
    currency: str,
    trade_date: date,
    fx_resolver: Optional[Callable[..., float]],
    txn_fx_rate: float | None,
) -> tuple[float | None, str | None]:
    native = (currency or "CAD").upper()
    if native == "CAD":
        return amount, None
    if txn_fx_rate is not None and txn_fx_rate > 0:
        return amount * txn_fx_rate, "transaction_reported_fx"
    if fx_resolver is None:
        return None, "withheld_mixed_currency"
    try:
        rate = float(fx_resolver(native, "CAD", trade_date))
    except TypeError:
        return None, "withheld_mixed_currency"
    if rate <= 0:
        return None, "withheld_mixed_currency"
    return amount * rate, "transaction_date_fx"


def _description(txn: Transaction) -> str:
    return (txn.description or "").lower()


def _is_return_of_capital(txn: Transaction) -> bool:
    return txn.action in {"distribution", "dividend", "corporate_action"} and "return of capital" in _description(txn)


def _is_reinvested_distribution(txn: Transaction) -> bool:
    if txn.action not in {"dividend", "distribution"}:
        return False
    description = _description(txn)
    return any(token in description for token in ("reinvest", "drip", "reinvested"))


def _within_superficial_window(left: date, right: date) -> bool:
    return abs((left - right).days) <= SUPERFICIAL_LOSS_WINDOW_DAYS


def _resolve_superficial_losses_on_buy(
    txn: Transaction,
    pool: _AcbPool,
    pending_losses: list[_SuperficialLossEvent],
    realized: list[RealizedTaxLot],
    blocked_symbols: set[str],
) -> int:
    adjustments = 0
    key = (txn.symbol.upper(), txn.con_id)
    for event in pending_losses:
        if event.resolved or (event.symbol, event.con_id) != key:
            continue
        if not _within_superficial_window(txn.trade_date, event.trade_date):
            continue
        pool.total_cost_cad += event.loss_amount
        event.resolved = True
        blocked_symbols.add(event.symbol)
        adjustments += 1
        if event.realized_index is not None and 0 <= event.realized_index < len(realized):
            lot = realized[event.realized_index]
            if lot.tax_realized_gain_loss is not None:
                adjusted_gain = lot.tax_realized_gain_loss + event.loss_amount
                realized[event.realized_index] = RealizedTaxLot(
                    symbol=lot.symbol,
                    tax_realized_gain_loss=round(adjusted_gain, 2),
                    short_term_gain_loss=lot.short_term_gain_loss,
                    long_term_gain_loss=lot.long_term_gain_loss,
                    quantity_sold=lot.quantity_sold,
                    proceeds=lot.proceeds,
                    cost_basis=round((lot.cost_basis or 0.0) + event.loss_amount, 2),
                    holding_period_days=lot.holding_period_days,
                    method=lot.method,
                    jurisdiction=lot.jurisdiction,
                    methodology_status="provisional_superficial_loss_adjusted",
                )
    return adjustments


def build_canadian_acb_report(
    account_id: str,
    transactions: list[Transaction],
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    fx_resolver: Optional[Callable[..., float]] = None,
    affiliated_accounts: list[str] | None = None,
) -> TaxAttributionReport:
    pools: dict[tuple[str, int | None], _AcbPool] = defaultdict(_AcbPool)
    realized: list[RealizedTaxLot] = []
    pending_losses: list[_SuperficialLossEvent] = []
    blocked_symbols: set[str] = set()
    fx_status: str | None = None
    superficial_adjustments = 0
    roc_adjustments = 0
    reinvest_adjustments = 0
    unsupported_events = 0

    if affiliated_accounts:
        methodology_status = "provisional_affiliated_data_present"
    else:
        methodology_status = "provisional_no_affiliated_accounts"

    ordered = sorted(
        (txn for txn in transactions if period_end is None or txn.trade_date <= period_end),
        key=lambda item: (item.trade_date, item.transaction_id or "", item.symbol, item.action),
    )

    for txn in ordered:
        key = (txn.symbol.upper(), txn.con_id)
        if txn.action in {"transfer", "transfer_in", "transfer_out"}:
            unsupported_events += 1
            continue

        if _is_return_of_capital(txn):
            pool = pools[key]
            if pool.quantity <= 1e-9:
                unsupported_events += 1
                continue
            amount = abs(txn.amount) if txn.amount is not None else abs(txn.quantity * txn.price)
            converted, status = _convert_to_cad(amount, txn.currency, txn.trade_date, fx_resolver, txn.fx_rate)
            if converted is None:
                fx_status = status
                continue
            if status:
                fx_status = status
            pool.total_cost_cad = max(0.0, pool.total_cost_cad - converted)
            roc_adjustments += 1
            continue

        if _is_reinvested_distribution(txn):
            pool = pools[key]
            amount = abs(txn.amount) if txn.amount is not None else abs(txn.quantity * txn.price)
            converted, status = _convert_to_cad(amount, txn.currency, txn.trade_date, fx_resolver, txn.fx_rate)
            if converted is None:
                fx_status = status
                continue
            if status:
                fx_status = status
            pool.total_cost_cad += converted
            reinvest_adjustments += 1
            continue

        if txn.action == "corporate_action":
            action = parse_corporate_action(txn)
            if action and action.action_type in {"split", "split_bonus"}:
                ratio = action.ratio if action.action_type == "split" else 2.0
                pool = pools[key]
                if pool.quantity > 0:
                    pool.quantity *= ratio
            elif _is_return_of_capital(txn):
                pass
            else:
                unsupported_events += 1
            continue

        if txn.action == "buy":
            notional = txn.price + (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
            converted, status = _convert_to_cad(
                notional * abs(txn.quantity),
                txn.currency,
                txn.trade_date,
                fx_resolver,
                txn.fx_rate,
            )
            if converted is None:
                fx_status = status
                continue
            if status:
                fx_status = status
            pool = pools[key]
            pool.quantity += abs(txn.quantity)
            pool.total_cost_cad += converted
            superficial_adjustments += _resolve_superficial_losses_on_buy(
                txn, pool, pending_losses, realized, blocked_symbols
            )
            continue

        if txn.action != "sell":
            if txn.action in {"deposit", "withdrawal", "fx", "fee", "interest", "withholding_tax"}:
                continue
            unsupported_events += 1
            continue

        if period_start and txn.trade_date < period_start:
            continue

        pool = pools[key]
        if pool.quantity <= 1e-9:
            realized.append(
                RealizedTaxLot(
                    symbol=txn.symbol.upper(),
                    tax_realized_gain_loss=None,
                    short_term_gain_loss=None,
                    long_term_gain_loss=None,
                    quantity_sold=abs(txn.quantity),
                    proceeds=None,
                    cost_basis=None,
                    holding_period_days=0,
                    method=TaxLotMethod.ACB,
                    jurisdiction="CA",
                    methodology_status=methodology_status,
                )
            )
            continue

        acb_per_share = pool.total_cost_cad / pool.quantity
        matched = min(abs(txn.quantity), pool.quantity)
        proceeds_per_share = txn.price - (txn.commission / abs(txn.quantity) if txn.quantity else 0.0)
        proceeds, status = _convert_to_cad(
            proceeds_per_share,
            txn.currency,
            txn.trade_date,
            fx_resolver,
            txn.fx_rate,
        )
        if proceeds is None:
            fx_status = status
            continue
        if status:
            fx_status = status
        cost = matched * acb_per_share
        gain = matched * proceeds - cost
        pool.quantity -= matched
        pool.total_cost_cad -= cost
        realized_index = len(realized)
        realized.append(
            RealizedTaxLot(
                symbol=txn.symbol.upper(),
                tax_realized_gain_loss=round(gain, 2),
                short_term_gain_loss=None,
                long_term_gain_loss=None,
                quantity_sold=round(matched, 6),
                proceeds=round(matched * proceeds, 2),
                cost_basis=round(cost, 2),
                holding_period_days=0,
                method=TaxLotMethod.ACB,
                jurisdiction="CA",
                methodology_status=methodology_status,
            )
        )
        if gain < 0:
            pending_losses.append(
                _SuperficialLossEvent(
                    trade_date=txn.trade_date,
                    symbol=txn.symbol.upper(),
                    con_id=txn.con_id,
                    loss_amount=abs(gain),
                    quantity=matched,
                    realized_index=realized_index,
                )
            )

    open_lots = [
        TaxLotSnapshot(
            account_id=account_id,
            symbol=symbol,
            con_id=con_id,
            quantity=round(pool.quantity, 6),
            cost_basis_per_share=round(pool.total_cost_cad / pool.quantity, 6) if pool.quantity > 0 else 0.0,
            acquired_date=period_end or date.today(),
            currency="CAD",
            jurisdiction="CA",
            method=TaxLotMethod.ACB,
        )
        for (symbol, con_id), pool in pools.items()
        if pool.quantity > 1e-9
    ]

    if fx_status == "withheld_mixed_currency":
        status = "incomplete"
        total = None
    elif realized or open_lots:
        status = "provisional"
        total = round(sum(item.tax_realized_gain_loss or 0.0 for item in realized), 2)
    else:
        status = "missing"
        total = None

    data_quality = {
        "status": status,
        "tax_lot_method": "acb",
        "tax_labeling_jurisdiction": "CA",
        "tax_compliance_status": methodology_status,
        "superficial_loss_adjustments": str(superficial_adjustments),
        "return_of_capital_adjustments": str(roc_adjustments),
        "reinvested_distribution_adjustments": str(reinvest_adjustments),
        "unsupported_event_count": str(unsupported_events),
    }
    if blocked_symbols:
        data_quality["superficial_loss_blocked_symbols"] = ",".join(sorted(blocked_symbols))
    if fx_status:
        data_quality["fx_conversion"] = fx_status

    return TaxAttributionReport(
        account_id=account_id,
        jurisdiction="CA",
        method=TaxLotMethod.ACB,
        methodology_status=methodology_status,
        reporting_currency="CAD",
        open_lots=open_lots,
        realized_lots=realized,
        total_tax_realized_gain_loss=total,
        total_short_term=None,
        total_long_term=None,
        unmatched_sell_quantity=round(
            sum(item.quantity_sold for item in realized if item.tax_realized_gain_loss is None),
            6,
        ),
        data_quality=data_quality,
        methodology=(
            "Canadian taxable reporting uses pooled adjusted cost base (ACB) in CAD with superficial-loss, "
            "return-of-capital, and reinvested-distribution adjustments. Option assignment/exercise, "
            "affiliated-account matching, and comprehensive corporate actions remain provisional."
        ),
        period_start=period_start,
        period_end=period_end,
    )
