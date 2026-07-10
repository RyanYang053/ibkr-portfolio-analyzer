from __future__ import annotations

from datetime import date
from typing import Callable

from pydantic import BaseModel, Field

from app.schemas.domain import Position, Transaction
from app.services.analytics.calculation_run import create_calculation_run, run_metadata_dict
from app.services.portfolio.ledger_coverage import (
    external_cash_flow_amount,
    ledger_covers_period,
    load_ledger_coverage,
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.transaction_store import get_transactions

RECONCILIATION_TOLERANCE_BPS = 25.0


class PositionPnLDecomposition(BaseModel):
    symbol: str
    price_effect: float | None = None
    fx_translation_effect: float | None = None
    trade_quantity_effect: float | None = None
    dividend_income: float = 0.0
    fee_expense: float = 0.0
    interest_income: float = 0.0
    corporate_action_effect: float = 0.0
    residual: float | None = None
    unexplained_pnl: float | None = None


class PortfolioPnLDecomposition(BaseModel):
    account_id: str
    period_start: date
    period_end: date
    reporting_currency: str
    account_value_change: float
    price_effect_total: float | None = None
    fx_translation_total: float | None = None
    trade_quantity_total: float | None = None
    dividend_income_total: float = 0.0
    fee_expense_total: float = 0.0
    interest_income_total: float = 0.0
    corporate_action_total: float = 0.0
    external_cash_flow_total: float = 0.0
    residual_total: float | None = None
    reconciliation_gap: float | None = None
    reconciliation_status: str = "withheld"
    positions: list[PositionPnLDecomposition] = Field(default_factory=list)
    calculation_run: dict[str, object] = Field(default_factory=dict)
    methodology: str = ""


def _signed_notional(txn: Transaction) -> float:
    if txn.amount is not None:
        return float(txn.amount)
    return float(txn.quantity) * float(txn.price)


def _convert_amount(
    amount: float,
    currency: str,
    base_currency: str,
    trade_date: date,
    fx_resolver: Callable,
) -> float:
    if currency.upper() == base_currency.upper():
        return amount
    rate = float(fx_resolver(currency, base_currency, trade_date))
    if rate <= 0:
        raise ValueError(f"Invalid FX rate for {currency}/{base_currency}: {rate}")
    return amount * rate


def _interval_transactions(
    transactions: list[Transaction],
    period_start: date,
    period_end: date,
) -> list[Transaction]:
    return [txn for txn in transactions if period_start < txn.trade_date <= period_end]


def calculate_pnl_decomposition(
    account_id: str,
    history: list[PortfolioPnLSnapshot],
    positions: list[Position],
    base_currency: str,
    fx_resolver: Callable,
) -> PortfolioPnLDecomposition:
    ordered = sorted(history, key=lambda row: (row.date, row.timestamp))
    if len(ordered) < 2:
        raise ValueError("At least two portfolio snapshots are required for PnL decomposition")

    period_start = date.fromisoformat(ordered[0].date)
    period_end = date.fromisoformat(ordered[-1].date)
    beginning_nav = float(ordered[0].net_liquidation)
    ending_nav = float(ordered[-1].net_liquidation)
    account_value_change = ending_nav - beginning_nav

    coverage = load_ledger_coverage(account_id)
    covers_period = ledger_covers_period(coverage, period_start, period_end)
    transactions = get_transactions(account_id)
    interval_txns = _interval_transactions(transactions, period_start, period_end)

    dividend_total = 0.0
    fee_total = 0.0
    interest_total = 0.0
    corporate_total = 0.0
    external_total = 0.0

    for txn in interval_txns:
        if txn.action == "dividend":
            dividend_total += abs(_convert_amount(_signed_notional(txn), txn.currency, base_currency, txn.trade_date, fx_resolver))
        elif txn.action == "fee":
            fee_total += abs(_convert_amount(_signed_notional(txn), txn.currency, base_currency, txn.trade_date, fx_resolver))
        elif txn.action in {"buy", "sell"}:
            fee_total += abs(_convert_amount(float(txn.commission or 0.0), txn.currency, base_currency, txn.trade_date, fx_resolver))
        elif txn.action == "interest":
            interest_total += abs(_convert_amount(_signed_notional(txn), txn.currency, base_currency, txn.trade_date, fx_resolver))
        elif txn.action == "corporate_action":
            corporate_total += _convert_amount(_signed_notional(txn), txn.currency, base_currency, txn.trade_date, fx_resolver)
        external_total += _convert_amount(
            external_cash_flow_amount(txn),
            txn.currency,
            base_currency,
            txn.trade_date,
            fx_resolver,
        )

    price_effect_total = None
    position_rows = [
        PositionPnLDecomposition(
            symbol=position.symbol,
            price_effect=None,
            dividend_income=round(
                sum(
                    abs(_convert_amount(_signed_notional(txn), txn.currency, base_currency, txn.trade_date, fx_resolver))
                    for txn in interval_txns
                    if txn.symbol == position.symbol and txn.action == "dividend"
                ),
                2,
            ),
            fee_expense=round(
                sum(
                    abs(_convert_amount(float(txn.commission or 0.0), txn.currency, base_currency, txn.trade_date, fx_resolver))
                    for txn in interval_txns
                    if txn.symbol == position.symbol and txn.action in {"buy", "sell"}
                )
                + sum(
                    abs(_convert_amount(_signed_notional(txn), txn.currency, base_currency, txn.trade_date, fx_resolver))
                    for txn in interval_txns
                    if txn.symbol == position.symbol and txn.action == "fee"
                ),
                2,
            ),
        )
        for position in positions
    ]

    investment_pnl = account_value_change - external_total
    explained = dividend_total + interest_total - fee_total + corporate_total
    residual_total = investment_pnl - explained
    tolerance_amount = abs(beginning_nav) * (RECONCILIATION_TOLERANCE_BPS / 10_000.0)
    reconciliation_status = "withheld_incomplete_ledger"
    if covers_period:
        reconciliation_status = "provisional_cash_flow_inventory"

    exclusions: list[str] = []
    if not covers_period:
        exclusions.append("ledger_incomplete")
    exclusions.extend(
        [
            "price_effect_withheld",
            "fx_translation_withheld",
            "trade_quantity_effect_withheld",
            "option_greek_effect_withheld",
        ]
    )

    snapshot_ids = [f"{row.date}:{row.timestamp}" for row in ordered]
    run = create_calculation_run(
        run_type="pnl_decomposition",
        account_id=account_id,
        input_snapshot_ids=snapshot_ids,
        transaction_batch_ids=[coverage.source] if coverage else [],
        exclusions=exclusions,
        coverage={
            "ledger_status": coverage.status if coverage else "missing",
            "reconciliation_status": reconciliation_status,
        },
    )

    methodology = (
        "Provisional cash-flow inventory: dividends, commissions/fees, interest, corporate actions, and external "
        "cash flows are inventoried for the selected period. Price, FX, trade-timing, and option effects are withheld "
        "until opening/closing lot-level accounting is complete. Investment PnL equals account value change minus "
        "net external flow."
    )
    if not covers_period:
        methodology += " Results are provisional because the activity ledger does not cover the full period."

    return PortfolioPnLDecomposition(
        account_id=account_id,
        period_start=period_start,
        period_end=period_end,
        reporting_currency=base_currency,
        account_value_change=round(account_value_change, 2),
        price_effect_total=None,
        fx_translation_total=None,
        trade_quantity_total=None,
        dividend_income_total=round(dividend_total, 2),
        fee_expense_total=round(fee_total, 2),
        interest_income_total=round(interest_total, 2),
        corporate_action_total=round(corporate_total, 2),
        external_cash_flow_total=round(external_total, 2),
        residual_total=round(residual_total, 2),
        reconciliation_gap=round(residual_total, 2),
        reconciliation_status=reconciliation_status,
        positions=position_rows,
        calculation_run=run_metadata_dict(run),
        methodology=methodology,
    )
