from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
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
    quantity_sold: float
    realized_index: int


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


def _resolve_superficial_losses(
    *,
    events: list[_SuperficialLossEvent],
    transactions: list[Transaction],
    affiliated_transactions: list[Transaction],
    realized: list[RealizedTaxLot],
    pools: dict[tuple[str, int | None], _AcbPool],
) -> tuple[set[str], int]:
    blocked_symbols: set[str] = set()
    adjustments = 0
    window_txns = list(transactions) + list(affiliated_transactions)

    for event in events:
        window_start = event.trade_date - timedelta(days=SUPERFICIAL_LOSS_WINDOW_DAYS)
        window_end = event.trade_date + timedelta(days=SUPERFICIAL_LOSS_WINDOW_DAYS)

        acquisitions = [
            txn
            for txn in window_txns
            if (
                txn.symbol.upper() == event.symbol
                and txn.action == "buy"
                and window_start <= txn.trade_date <= window_end
            )
        ]

        acquired_quantity = sum(abs(txn.quantity) for txn in acquisitions)

        affiliated_net_still_owned = 0.0
        for txn in affiliated_transactions:
            if txn.symbol.upper() != event.symbol:
                continue
            if not (window_start <= txn.trade_date <= window_end):
                continue
            if txn.action == "buy":
                affiliated_net_still_owned += abs(txn.quantity)
            elif txn.action == "sell":
                affiliated_net_still_owned -= abs(txn.quantity)
        affiliated_net_still_owned = max(affiliated_net_still_owned, 0.0)

        pool = pools[(event.symbol, event.con_id)]
        substituted_quantity_still_owned = min(
            acquired_quantity,
            max(pool.quantity, 0.0) + affiliated_net_still_owned,
            event.quantity_sold,
        )

        if substituted_quantity_still_owned <= 0:
            continue

        denied_fraction = substituted_quantity_still_owned / event.quantity_sold
        denied_loss = event.loss_amount * denied_fraction

        # Add denied loss back only to the seller's remaining ACB when they still own shares.
        primary_addback = min(denied_loss, denied_loss * (max(pool.quantity, 0.0) / substituted_quantity_still_owned))
        if pool.quantity > 0:
            pool.total_cost_cad += primary_addback
        blocked_symbols.add(event.symbol)
        adjustments += 1

        lot = realized[event.realized_index]
        realized[event.realized_index] = replace(
            lot,
            tax_realized_gain_loss=round(
                (lot.tax_realized_gain_loss or 0.0) + denied_loss,
                2,
            ),
            cost_basis=round(
                (lot.cost_basis or 0.0) + denied_loss,
                2,
            ),
            methodology_status="provisional_superficial_loss_adjusted",
        )

    return blocked_symbols, adjustments


def build_canadian_acb_report(
    account_id: str,
    transactions: list[Transaction],
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    fx_resolver: Optional[Callable[..., float]] = None,
    affiliated_accounts: list[str] | None = None,
    affiliated_transactions: list[Transaction] | None = None,
) -> TaxAttributionReport:
    pools: dict[tuple[str, int | None], _AcbPool] = defaultdict(_AcbPool)
    realized: list[RealizedTaxLot] = []
    pending_losses: list[_SuperficialLossEvent] = []
    fx_status: str | None = None
    superficial_adjustments = 0
    roc_adjustments = 0
    reinvest_adjustments = 0
    unsupported_events = 0
    affiliated_txns = list(affiliated_transactions or [])

    if affiliated_accounts and affiliated_txns:
        methodology_status = "affiliated_accounts_applied"
    elif affiliated_accounts:
        methodology_status = "provisional_affiliated_accounts_missing_transactions"
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
                    quantity_sold=matched,
                    realized_index=realized_index,
                )
            )

    blocked_symbols, superficial_adjustments = _resolve_superficial_losses(
        events=pending_losses,
        transactions=ordered,
        affiliated_transactions=affiliated_txns,
        realized=realized,
        pools=pools,
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
    if affiliated_accounts:
        data_quality["affiliated_account_count"] = str(len(affiliated_accounts))
        data_quality["affiliated_transaction_count"] = str(len(affiliated_txns))

    methodology = (
        "Canadian taxable reporting uses pooled adjusted cost base (ACB) in CAD with superficial-loss, "
        "return-of-capital, and reinvested-distribution adjustments."
    )
    if methodology_status == "affiliated_accounts_applied":
        methodology += (
            " Affiliated-account acquisitions inside the +/-30 day window are included when resolving "
            "superficial losses."
        )
    else:
        methodology += (
            " Option assignment/exercise and comprehensive corporate actions remain provisional; "
            "affiliated-account coverage depends on configured household linkages and loaded ledgers."
        )

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
        methodology=methodology,
        period_start=period_start,
        period_end=period_end,
    )
