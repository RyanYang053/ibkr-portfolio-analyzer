from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Optional

from app.schemas.domain import Transaction
from app.services.portfolio.corporate_actions import apply_corporate_action_to_lots, parse_corporate_action
from app.services.tax.models import RealizedTaxLot, TaxAttributionReport, TaxLotMethod, TaxLotSnapshot


@dataclass
class _AcbPool:
    quantity: float = 0.0
    total_cost_cad: float = 0.0


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
    fx_status: str | None = None
    methodology_status = "provisional"
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
        if txn.action == "corporate_action":
            action = parse_corporate_action(txn)
            if action and action.action_type in {"split", "split_bonus"}:
                ratio = action.ratio if action.action_type == "split" else 2.0
                pool = pools[key]
                if pool.quantity > 0:
                    pool.quantity *= ratio
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
        data_quality={
            "status": status,
            "tax_lot_method": "acb",
            "tax_labeling_jurisdiction": "CA",
            "tax_compliance_status": methodology_status,
            **({"fx_conversion": fx_status} if fx_status else {}),
        },
        methodology=(
            "Canadian taxable reporting uses pooled adjusted cost base (ACB) in CAD. "
            "Superficial-loss adjustments require affiliated-account data and remain provisional."
        ),
        period_start=period_start,
        period_end=period_end,
    )
