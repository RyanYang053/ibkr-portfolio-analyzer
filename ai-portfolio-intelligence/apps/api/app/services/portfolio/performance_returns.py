from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from app.schemas.domain import PerformanceReturns, Transaction
from app.services.portfolio.ledger_coverage import (
    external_cash_flow_amount,
    external_cash_flows_for_interval,
    ledger_covers_period,
    load_ledger_coverage,
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.transaction_store import get_transactions


def _daily_investment_returns(
    history: list[PortfolioPnLSnapshot],
    transactions: list[Transaction],
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
) -> list[dict[str, float | str]]:
    ordered = sorted(history, key=lambda item: (item.date, item.timestamp))
    rows: list[dict[str, float | str]] = []
    previous_nav: float | None = None
    previous_date: date | None = None

    for snapshot in ordered:
        nav = snapshot.net_liquidation
        current_date = date.fromisoformat(snapshot.date)
        cash_flow = 0.0
        if previous_date is not None:
            cash_flow = external_cash_flows_for_interval(
                transactions,
                previous_date,
                current_date,
                base_currency,
                fx_resolver,
            )
        if previous_nav is not None and previous_nav != 0:
            investment_return = (nav - cash_flow) / previous_nav - 1.0
        else:
            investment_return = 0.0
        rows.append(
            {
                "date": snapshot.date,
                "net_liquidation": round(nav, 2),
                "external_cash_flow": round(cash_flow, 2),
                "investment_return_percent": round(investment_return * 100.0, 4),
            }
        )
        previous_nav = nav
        previous_date = current_date
    return rows


def calculate_time_weighted_return(daily_returns: list[float]) -> float | None:
    if not daily_returns:
        return None
    compounded = 1.0
    for value in daily_returns:
        compounded *= 1.0 + value
    return compounded - 1.0


def _xnpv(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    if not cash_flows:
        return 0.0
    base = cash_flows[0][0].toordinal()
    total = 0.0
    for flow_date, amount in cash_flows:
        years = (flow_date.toordinal() - base) / 365.0
        total += amount / ((1.0 + rate) ** years)
    return total


def _xnpv_derivative(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    if not cash_flows:
        return 0.0
    base = cash_flows[0][0].toordinal()
    total = 0.0
    for flow_date, amount in cash_flows:
        years = (flow_date.toordinal() - base) / 365.0
        if years == 0:
            continue
        total -= years * amount / ((1.0 + rate) ** (years + 1.0))
    return total


def calculate_xirr(cash_flows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    if len(cash_flows) < 2:
        return None
    if not any(amount < 0 for _, amount in cash_flows) or not any(amount > 0 for _, amount in cash_flows):
        return None

    rate = guess
    for _ in range(100):
        value = _xnpv(rate, cash_flows)
        derivative = _xnpv_derivative(rate, cash_flows)
        if abs(derivative) < 1e-12:
            break
        next_rate = rate - value / derivative
        if not math.isfinite(next_rate):
            break
        if abs(next_rate - rate) < 1e-7:
            return next_rate
        rate = max(-0.999, min(next_rate, 10.0))
    return None


def build_xirr_cash_flows(
    transactions: list[Transaction],
    opening_nav: float,
    opening_date: date,
    terminal_nav: float,
    terminal_date: date,
    period_start: date,
    period_end: date,
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
) -> list[tuple[date, float]]:
    """Investor perspective: opening NAV negative, external contributions negative, distributions positive, terminal NAV positive."""
    flows: list[tuple[date, float]] = []
    if opening_nav > 0:
        flows.append((opening_date, -opening_nav))

    for txn in transactions:
        if txn.trade_date < period_start or txn.trade_date > period_end:
            continue
        amount = external_cash_flow_amount(txn)
        if amount == 0.0:
            continue
        rate = fx_resolver(txn.currency, base_currency)
        signed = amount * rate
        # External inflow to account is investor contribution (negative); outflow is distribution (positive).
        flows.append((txn.trade_date, -signed))

    if terminal_nav > 0:
        flows.append((terminal_date, terminal_nav))
    flows.sort(key=lambda item: item[0])
    return flows


def calculate_performance_returns(
    account_id: str,
    history: list[PortfolioPnLSnapshot],
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
    allow_mock: bool = False,
) -> PerformanceReturns:
    transactions = get_transactions(account_id)
    coverage = load_ledger_coverage(account_id)
    ordered = sorted(history, key=lambda item: (item.date, item.timestamp))

    period_start = date.fromisoformat(ordered[0].date) if ordered else date.today()
    period_end = date.fromisoformat(ordered[-1].date) if ordered else date.today()
    period_days = max((period_end - period_start).days, 0)

    daily_rows = _daily_investment_returns(history, transactions, base_currency, fx_resolver)
    daily_return_values = [float(row["investment_return_percent"]) / 100.0 for row in daily_rows[1:]]

    covers_period = ledger_covers_period(coverage, period_start, period_end)
    twr = calculate_time_weighted_return(daily_return_values) if covers_period and len(daily_return_values) > 0 else None
    twr_annualized = None
    if twr is not None and period_days > 0:
        twr_annualized = (1.0 + twr) ** (365.0 / period_days) - 1.0

    opening_nav = ordered[0].net_liquidation if ordered else 0.0
    terminal_nav = ordered[-1].net_liquidation if ordered else 0.0
    xirr = None
    if covers_period and ordered:
        xirr_flows = build_xirr_cash_flows(
            transactions,
            opening_nav,
            period_start,
            terminal_nav,
            period_end,
            period_start,
            period_end,
            base_currency,
            fx_resolver,
        )
        xirr = calculate_xirr(xirr_flows)

    from app.services.portfolio.benchmark_returns import align_benchmark_comparison

    portfolio_twr_percent = round(twr * 100.0, 4) if twr is not None else None
    benchmark_comparison = align_benchmark_comparison(
        history,
        portfolio_twr_percent=portfolio_twr_percent,
        allow_mock=allow_mock,
    )

    cash_flow_status = "sufficient" if covers_period else "missing"
    if coverage and coverage.execution_only:
        cash_flow_status = "partial_execution_only"

    data_quality = {
        "cash_flow_adjustment": cash_flow_status,
        "history_observations": str(len(history)),
        "transaction_count": str(len(transactions)),
        "ledger_status": coverage.status if coverage else "missing",
        "ledger_execution_only": str(coverage.execution_only if coverage else False),
        "benchmark_series": str(benchmark_comparison.get("status", "missing")),
    }

    methodology = (
        "Time-weighted return compounds interval investment returns after removing external cash flows "
        "assigned to the portfolio snapshot interval. Weekend and holiday external flows are included in "
        "the following snapshot interval. XIRR uses opening NAV, external contributions/distributions, and "
        "terminal NAV. Dividends, interest, fees, and trade executions are internal activity."
    )
    if not covers_period:
        methodology += " TWR and XIRR are withheld because the external-cash-flow ledger does not cover the full measurement period."

    return PerformanceReturns(
        time_weighted_return=portfolio_twr_percent,
        time_weighted_return_annualized=round(twr_annualized * 100.0, 4) if twr_annualized is not None else None,
        xirr=round(xirr * 100.0, 4) if xirr is not None else None,
        period_days=period_days,
        observation_count=len(history),
        daily_returns=daily_rows,
        benchmark_comparison=benchmark_comparison,
        data_quality=data_quality,
        methodology=methodology,
    )
