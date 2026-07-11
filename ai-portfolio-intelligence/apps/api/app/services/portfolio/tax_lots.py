from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Callable, Deque, Literal, Optional

from app.schemas.domain import RealizedLotAttribution, TaxLot, TaxLotAttributionReport, Transaction
from app.services.portfolio.corporate_actions import apply_corporate_action_to_lots, parse_corporate_action
from app.services.tax.canadian_acb import build_canadian_acb_report
from app.services.tax.models import TaxLotMethod
from app.services.tax.us_tax_lots import build_us_tax_lot_report

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


def _is_long_term_us(acquired: date, sold: date) -> bool:
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:
        anniversary = acquired.replace(year=acquired.year + 1, day=28)
    return sold > anniversary


def _consume_sell(
    open_lots: dict[tuple[str, int | None], Deque[_OpenLot]],
    txn: Transaction,
    reporting_currency: str,
    tax_labeling_jurisdiction: Literal["US", "CA", "OTHER"],
    fx_resolver: Optional[Callable[..., float]],
    emit_realized: bool,
) -> tuple[Optional[RealizedLotAttribution], Optional[str]]:
    key = _lot_key(txn)
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
        return None, status

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
        if tax_labeling_jurisdiction == "US" and emit_realized:
            if _is_long_term_us(lot.acquired_date, txn.trade_date):
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

    if not emit_realized:
        return None, status

    gain_loss = round(total_proceeds - total_cost, 2)
    return (
        RealizedLotAttribution(
            symbol=txn.symbol.upper(),
            tax_realized_gain_loss=gain_loss,
            realized_gain_loss=gain_loss,
            short_term_gain_loss=round(short_term, 2) if tax_labeling_jurisdiction == "US" else None,
            long_term_gain_loss=round(long_term, 2) if tax_labeling_jurisdiction == "US" else None,
            quantity_sold=round(matched_qty, 6),
            unmatched_sell_quantity=round(remaining, 6),
            proceeds=round(total_proceeds, 2),
            cost_basis=round(total_cost, 2),
            holding_period_days=max_holding_days,
        ),
        status,
    )


def _report_from_us(report) -> TaxLotAttributionReport:
    return TaxLotAttributionReport(
        account_id=report.account_id,
        lots_open=[
            TaxLot(
                account_id=report.account_id,
                symbol=lot.symbol,
                con_id=lot.con_id,
                quantity=lot.quantity,
                cost_basis_per_share=lot.cost_basis_per_share,
                acquired_date=lot.acquired_date,
                currency=lot.currency,
            )
            for lot in report.open_lots
        ],
        realized_by_symbol=[
            RealizedLotAttribution(
                symbol=row.symbol,
                tax_realized_gain_loss=row.tax_realized_gain_loss or 0.0,
                realized_gain_loss=row.tax_realized_gain_loss or 0.0,
                short_term_gain_loss=row.short_term_gain_loss,
                long_term_gain_loss=row.long_term_gain_loss,
                quantity_sold=row.quantity_sold,
                unmatched_sell_quantity=row.unmatched_sell_quantity,
                proceeds=row.proceeds or 0.0,
                cost_basis=row.cost_basis or 0.0,
                holding_period_days=row.holding_period_days,
                method=row.method.value,
            )
            for row in report.realized_lots
        ],
        total_realized_gain_loss=report.total_tax_realized_gain_loss,
        total_short_term=report.total_short_term,
        total_long_term=report.total_long_term,
        reporting_currency=report.reporting_currency,
        jurisdiction=report.jurisdiction,
        methodology_status=report.methodology_status,
        period_start=report.period_start,
        period_end=report.period_end,
        unmatched_sell_quantity=report.unmatched_sell_quantity,
        data_quality=report.data_quality,
        methodology=report.methodology,
    )


def build_tax_lot_attribution(
    account_id: str,
    transactions: list[Transaction],
    reporting_currency: str = "USD",
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    tax_labeling_jurisdiction: Literal["US", "CA", "OTHER"] = "OTHER",
    fx_resolver: Optional[Callable[..., float]] = None,
) -> TaxLotAttributionReport:
    if tax_labeling_jurisdiction == "CA":
        if not transactions:
            return TaxLotAttributionReport(
                account_id=account_id,
                lots_open=[],
                realized_by_symbol=[],
                total_realized_gain_loss=None,
                total_short_term=None,
                total_long_term=None,
                reporting_currency="CAD",
                jurisdiction="CA",
                methodology_status="withheld",
                period_start=period_start,
                period_end=period_end,
                unmatched_sell_quantity=0.0,
                data_quality={
                    "status": "unavailable",
                    "tax_lot_method": "acb_withheld",
                    "tax_labeling_jurisdiction": "CA",
                },
                methodology=(
                    "Canadian taxable reporting requires pooled adjusted cost base (ACB) in CAD with superficial-loss "
                    "rules. FIFO tax-lot output is withheld for Canadian residency."
                ),
            )
        ca_report = build_canadian_acb_report(
            account_id,
            transactions,
            period_start=period_start,
            period_end=period_end,
            fx_resolver=fx_resolver,
        )
        return TaxLotAttributionReport(
            account_id=account_id,
            lots_open=[
                TaxLot(
                    account_id=account_id,
                    symbol=lot.symbol,
                    con_id=lot.con_id,
                    quantity=lot.quantity,
                    cost_basis_per_share=lot.cost_basis_per_share,
                    acquired_date=lot.acquired_date,
                    currency=lot.currency,
                )
                for lot in ca_report.open_lots
            ],
            realized_by_symbol=[
                RealizedLotAttribution(
                    symbol=row.symbol,
                    tax_realized_gain_loss=row.tax_realized_gain_loss if row.tax_realized_gain_loss is not None else 0.0,
                    realized_gain_loss=row.tax_realized_gain_loss if row.tax_realized_gain_loss is not None else 0.0,
                    quantity_sold=row.quantity_sold,
                    proceeds=row.proceeds or 0.0,
                    cost_basis=row.cost_basis or 0.0,
                    holding_period_days=row.holding_period_days,
                    method=row.method.value,
                )
                for row in ca_report.realized_lots
            ],
            total_realized_gain_loss=ca_report.total_tax_realized_gain_loss,
            total_short_term=None,
            total_long_term=None,
            reporting_currency="CAD",
            jurisdiction="CA",
            methodology_status=ca_report.methodology_status,
            period_start=period_start,
            period_end=period_end,
            unmatched_sell_quantity=ca_report.unmatched_sell_quantity,
            data_quality=ca_report.data_quality,
            methodology=ca_report.methodology,
        )

    if tax_labeling_jurisdiction == "US":
        return _report_from_us(
            build_us_tax_lot_report(
                account_id,
                transactions,
                reporting_currency=reporting_currency,
                period_start=period_start,
                period_end=period_end,
                lot_method=TaxLotMethod.FIFO,
                fx_resolver=fx_resolver,
            )
        )

    open_lots: dict[tuple[str, int | None], Deque[_OpenLot]] = defaultdict(deque)
    realized_rows: list[RealizedLotAttribution] = []
    execution_rows = [txn for txn in transactions if txn.action in EXECUTION_ACTIONS]
    corporate_rows = [txn for txn in transactions if txn.action in CORPORATE_ACTIONS]
    buys_before_period = 0
    fx_status: Optional[str] = None

    ordered = sorted(
        (
            txn
            for txn in transactions
            if period_end is None or txn.trade_date <= period_end
        ),
        key=lambda item: (
            item.trade_date,
            item.transaction_id or "",
            item.symbol,
            item.action,
        ),
    )

    for txn in ordered:
        key = _lot_key(txn)
        if txn.action == "corporate_action":
            action = parse_corporate_action(txn)
            if action is None:
                continue
            if open_lots[key]:
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

        emit_realized = period_start is None or txn.trade_date >= period_start
        realized_row, status = _consume_sell(
            open_lots,
            txn,
            reporting_currency,
            tax_labeling_jurisdiction,
            fx_resolver,
            emit_realized,
        )
        if status:
            fx_status = status
        if realized_row is not None:
            realized_rows.append(realized_row)

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

    unparsed_corporate_actions = [txn for txn in corporate_rows if parse_corporate_action(txn) is None]
    corp_note = None

    if fx_status == "withheld_mixed_currency" or (mixed_currency and fx_resolver is None):
        status = "incomplete"
    elif unparsed_corporate_actions:
        status = "incomplete"
        corp_note = "corporate_actions_partial"
    elif incomplete_opening_lots or has_unmatched:
        status = "incomplete"
    elif realized_rows or open_rows:
        status = "lot_matching_complete"
        if corporate_rows:
            corp_note = "corporate_actions_applied"
    else:
        status = "missing"

    total_realized = (
        round(sum(row.tax_realized_gain_loss for row in realized_rows), 2)
        if status == "lot_matching_complete"
        else None
    )
    total_short = (
        round(sum(row.short_term_gain_loss or 0.0 for row in realized_rows), 2)
        if status == "lot_matching_complete"
        else None
    )
    total_long = (
        round(sum(row.long_term_gain_loss or 0.0 for row in realized_rows), 2)
        if status == "lot_matching_complete"
        else None
    )

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
    if corporate_rows and unparsed_corporate_actions:
        methodology += " Some corporate actions could not be parsed; output is withheld."
    elif corporate_rows:
        methodology += " Supported corporate actions (stock splits) are applied to FIFO tax lots."

    data_quality = {
        "tax_lot_method": "fifo",
        "transaction_count": str(len(transactions)),
        "execution_count": str(len(execution_rows)),
        "status": status,
        "tax_compliance_status": "experimental",
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
        total_short_term=total_short if tax_labeling_jurisdiction == "US" else None,
        total_long_term=total_long if tax_labeling_jurisdiction == "US" else None,
        reporting_currency=reporting_currency,
        jurisdiction=tax_labeling_jurisdiction,
        methodology_status="experimental",
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
    if report.data_quality.get("status") != "lot_matching_complete":
        return {}
    grouped: dict[str, float] = defaultdict(float)
    for row in report.realized_by_symbol:
        grouped[row.symbol] += row.tax_realized_gain_loss
    return {symbol: round(value, 2) for symbol, value in grouped.items()}
