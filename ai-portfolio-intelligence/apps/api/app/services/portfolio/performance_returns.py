from __future__ import annotations

import math
from datetime import date, datetime
from typing import Callable, Optional

from app.schemas.domain import PerformanceReturns
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.transaction_store import external_cash_flows_by_date, get_transactions


def _daily_investment_returns(
    history: list[PortfolioPnLSnapshot],
    cash_flows_by_date: dict[str, float],
) -> list[dict[str, float | str]]:
    ordered = sorted(history, key=lambda item: (item.date, item.timestamp))
    rows: list[dict[str, float | str]] = []
    previous_nav: float | None = None
    for snapshot in ordered:
        nav = snapshot.net_liquidation
        cash_flow = cash_flows_by_date.get(snapshot.date, 0.0)
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
    """Money-weighted return using Newton-Raphson on dated cash flows."""
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
    transactions: list,
    terminal_nav: float,
    terminal_date: date,
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
) -> list[tuple[date, float]]:
    """Investor perspective: deposits negative, withdrawals/dividends/terminal value positive."""
    flows: list[tuple[date, float]] = []
    for txn in transactions:
        amount = txn.amount if txn.amount is not None else txn.quantity * txn.price
        rate = fx_resolver(txn.currency, base_currency)
        signed = amount * rate
        if txn.action == "deposit":
            flows.append((txn.trade_date, -abs(signed)))
        elif txn.action == "withdrawal":
            flows.append((txn.trade_date, abs(signed)))
        elif txn.action == "dividend":
            flows.append((txn.trade_date, abs(signed)))
    if terminal_nav > 0:
        flows.append((terminal_date, terminal_nav))
    flows.sort(key=lambda item: item[0])
    return flows


def calculate_performance_returns(
    account_id: str,
    history: list[PortfolioPnLSnapshot],
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
) -> PerformanceReturns:
    transactions = get_transactions(account_id)
    cash_flows_by_date = external_cash_flows_by_date(transactions, base_currency, fx_resolver)
    daily_rows = _daily_investment_returns(history, cash_flows_by_date)
    daily_return_values = [float(row["investment_return_percent"]) / 100.0 for row in daily_rows[1:]]
    twr = calculate_time_weighted_return(daily_return_values)

    period_days = 0
    if len(history) >= 2:
        start = date.fromisoformat(sorted(history, key=lambda item: item.date)[0].date)
        end = date.fromisoformat(sorted(history, key=lambda item: item.date)[-1].date)
        period_days = max((end - start).days, 0)

    twr_annualized = None
    if twr is not None and period_days > 0:
        twr_annualized = (1.0 + twr) ** (365.0 / period_days) - 1.0

    terminal_nav = history[-1].net_liquidation if history else 0.0
    terminal_date = date.fromisoformat(history[-1].date) if history else date.today()
    xirr_flows = build_xirr_cash_flows(transactions, terminal_nav, terminal_date, base_currency, fx_resolver)
    xirr = calculate_xirr(xirr_flows)

    has_cash_flows = bool(transactions)
    data_quality = {
        "cash_flow_adjustment": "sufficient" if has_cash_flows else "missing",
        "history_observations": str(len(history)),
        "transaction_count": str(len(transactions)),
    }
    methodology = (
        "Time-weighted return compounds daily investment returns after removing dated external cash flows. "
        "XIRR solves the money-weighted return using deposits, withdrawals, dividends, and terminal net liquidation."
    )
    if not has_cash_flows:
        methodology += " External cash flows are missing; TWR uses zero-flow assumption and XIRR is withheld."

    return PerformanceReturns(
        time_weighted_return=round(twr * 100.0, 4) if twr is not None else None,
        time_weighted_return_annualized=round(twr_annualized * 100.0, 4) if twr_annualized is not None else None,
        xirr=round(xirr * 100.0, 4) if xirr is not None and has_cash_flows else None,
        period_days=period_days,
        observation_count=len(history),
        daily_returns=daily_rows,
        data_quality=data_quality,
        methodology=methodology,
    )
