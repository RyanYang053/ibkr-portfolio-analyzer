from __future__ import annotations

import math
from datetime import date
from typing import Callable

from app.schemas.domain import PerformanceReturns, Transaction
from app.services.portfolio.ledger_coverage import (
    external_cash_flow_amount,
    external_cash_flows_for_interval,
    ledger_covers_period,
    load_ledger_coverage,
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.transaction_store import get_transactions

MIN_ANNUALIZATION_DAYS = 30
METHODOLOGY_VERSION = "2026.07.2"


def _latest_daily_snapshots(history: list[PortfolioPnLSnapshot]) -> list[PortfolioPnLSnapshot]:
    """Keep the latest observation for each date to avoid intraday double counting."""
    by_date: dict[str, PortfolioPnLSnapshot] = {}
    for item in sorted(history, key=lambda row: (row.date, row.timestamp)):
        by_date[item.date] = item
    return [by_date[key] for key in sorted(by_date)]


def _flow_weight(trade_date: date, interval_start: date, interval_end: date) -> float:
    total_days = max((interval_end - interval_start).days, 1)
    remaining = max((interval_end - trade_date).days, 0)
    return min(max(remaining / total_days, 0.0), 1.0)


def _modified_dietz_interval_return(
    beginning_nav: float,
    ending_nav: float,
    transactions: list[Transaction],
    interval_start: date,
    interval_end: date,
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
) -> float | None:
    if beginning_nav <= 0:
        return None
    weighted_flow = 0.0
    total_flow = 0.0
    for txn in transactions:
        if txn.trade_date <= interval_start or txn.trade_date > interval_end:
            continue
        amount = external_cash_flow_amount(txn)
        if amount == 0.0:
            continue
        if txn.currency.upper() == base_currency.upper():
            rate = 1.0
        else:
            rate = float(fx_resolver(txn.currency, base_currency, txn.trade_date))
        converted = amount * rate
        total_flow += converted
        weighted_flow += _flow_weight(txn.trade_date, interval_start, interval_end) * converted
    denominator = beginning_nav + weighted_flow
    if denominator <= 0:
        return None
    interval_return = (ending_nav - beginning_nav - total_flow) / denominator
    if not math.isfinite(interval_return) or interval_return <= -1.0:
        return None
    return interval_return


def _interval_external_flows(
    transactions: list[Transaction],
    interval_start: date,
    interval_end: date,
) -> list[Transaction]:
    return [
        txn
        for txn in transactions
        if interval_start < txn.trade_date <= interval_end and external_cash_flow_amount(txn) != 0.0
    ]


def _subperiod_twr_interval_return(
    snapshots: list[PortfolioPnLSnapshot],
    transactions: list[Transaction],
    interval_start: date,
    interval_end: date,
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
) -> float | None:
    """Exact subperiod linking when NAV observations exist on flow dates."""
    flows = _interval_external_flows(transactions, interval_start, interval_end)
    if not flows:
        return None

    flow_dates = sorted({txn.trade_date for txn in flows})
    nav_by_date = {date.fromisoformat(item.date): float(item.net_liquidation) for item in snapshots}
    if date.fromisoformat(snapshots[0].date) != interval_start or date.fromisoformat(snapshots[-1].date) != interval_end:
        return None
    if not all(flow_date in nav_by_date for flow_date in flow_dates):
        return None
    # A same-day NAV cannot bracket a flow; exact subperiod linking requires pre/post-flow valuations.
    if any(flow_date in {interval_start, interval_end} for flow_date in flow_dates):
        return None

    boundaries = [interval_start, *flow_dates, interval_end]
    compounded = 1.0
    for left, right in zip(boundaries, boundaries[1:]):
        beginning = nav_by_date[left]
        ending = nav_by_date[right]
        if beginning <= 0:
            return None
        sub_flow = sum(
            external_cash_flow_amount(txn)
            * (
                1.0
                if txn.currency.upper() == base_currency.upper()
                else float(fx_resolver(txn.currency, base_currency, txn.trade_date))
            )
            for txn in flows
            if left < txn.trade_date <= right
        )
        sub_return = (ending - beginning - sub_flow) / beginning
        if not math.isfinite(sub_return) or sub_return <= -1.0:
            return None
        compounded *= 1.0 + sub_return
    return compounded - 1.0


def _daily_investment_returns(
    history: list[PortfolioPnLSnapshot],
    transactions: list[Transaction],
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
    *,
    ledger_complete: bool,
) -> list[dict[str, float | str]]:
    ordered = _latest_daily_snapshots(history)
    rows: list[dict[str, float | str]] = []
    previous_nav: float | None = None
    previous_date: date | None = None

    for snapshot in ordered:
        nav = float(snapshot.net_liquidation)
        current_date = date.fromisoformat(snapshot.date)
        row: dict[str, float | str] = {
            "date": snapshot.date,
            "net_liquidation": round(nav, 2),
        }

        if previous_nav is None:
            row["external_cash_flow"] = 0.0
            row["investment_return_percent"] = 0.0
            row["return_status"] = "opening_observation"
        elif ledger_complete and previous_date is not None and previous_nav > 0:
            cash_flow = external_cash_flows_for_interval(
                transactions,
                previous_date,
                current_date,
                base_currency,
                fx_resolver,
            )
            interval_snapshots = [
                item
                for item in ordered
                if previous_date <= date.fromisoformat(item.date) <= current_date
            ]
            subperiod_return = _subperiod_twr_interval_return(
                interval_snapshots,
                transactions,
                previous_date,
                current_date,
                base_currency,
                fx_resolver,
            )
            if subperiod_return is not None:
                investment_return = subperiod_return
                return_status = "subperiod_twr"
            elif cash_flow != 0.0:
                dietz_return = _modified_dietz_interval_return(
                    previous_nav,
                    nav,
                    transactions,
                    previous_date,
                    current_date,
                    base_currency,
                    fx_resolver,
                )
                if dietz_return is None:
                    row["return_status"] = "withheld_invalid_interval"
                    rows.append(row)
                    previous_nav = nav
                    previous_date = current_date
                    continue
                investment_return = dietz_return
                return_status = "modified_dietz"
            else:
                investment_return = (nav - cash_flow) / previous_nav - 1.0
                return_status = "cash_flow_adjusted"
            if not math.isfinite(investment_return) or investment_return <= -1.0:
                row["return_status"] = "withheld_invalid_interval"
            else:
                row["external_cash_flow"] = round(cash_flow, 2)
                row["investment_return_percent"] = round(investment_return * 100.0, 6)
                row["return_status"] = return_status
        else:
            row["return_status"] = "withheld_incomplete_ledger"

        rows.append(row)
        previous_nav = nav
        previous_date = current_date
    return rows


def calculate_time_weighted_return(daily_returns: list[float]) -> float | None:
    if not daily_returns:
        return None
    compounded = 1.0
    for value in daily_returns:
        if not math.isfinite(value) or value <= -1.0:
            return None
        compounded *= 1.0 + value
    return compounded - 1.0


def _xnpv(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    if not cash_flows or rate <= -1.0:
        return math.inf
    base = cash_flows[0][0].toordinal()
    return sum(
        amount / ((1.0 + rate) ** ((flow_date.toordinal() - base) / 365.0))
        for flow_date, amount in cash_flows
    )


def _xnpv_derivative(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    if not cash_flows or rate <= -1.0:
        return 0.0
    base = cash_flows[0][0].toordinal()
    total = 0.0
    for flow_date, amount in cash_flows:
        years = (flow_date.toordinal() - base) / 365.0
        if years:
            total -= years * amount / ((1.0 + rate) ** (years + 1.0))
    return total


def calculate_xirr(cash_flows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Solve XIRR with Newton first and a bounded bracket fallback."""
    if len(cash_flows) < 2:
        return None
    if not any(amount < 0 for _, amount in cash_flows) or not any(amount > 0 for _, amount in cash_flows):
        return None

    ordered = sorted(cash_flows, key=lambda item: item[0])
    rate = max(-0.95, guess)
    for _ in range(50):
        value = _xnpv(rate, ordered)
        derivative = _xnpv_derivative(rate, ordered)
        if not math.isfinite(value) or abs(derivative) < 1e-12:
            break
        candidate = rate - value / derivative
        if not math.isfinite(candidate) or candidate <= -1.0 or candidate > 100.0:
            break
        if abs(candidate - rate) < 1e-9:
            return candidate
        rate = candidate

    grid = [-0.9999, -0.95, -0.9, -0.75, -0.5, -0.25, 0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 100.0]
    previous_rate = grid[0]
    previous_value = _xnpv(previous_rate, ordered)
    for current_rate in grid[1:]:
        current_value = _xnpv(current_rate, ordered)
        if math.isfinite(previous_value) and math.isfinite(current_value):
            if previous_value == 0:
                return previous_rate
            if previous_value * current_value < 0:
                low, high = previous_rate, current_rate
                for _ in range(120):
                    mid = (low + high) / 2.0
                    mid_value = _xnpv(mid, ordered)
                    if abs(mid_value) < 1e-8 or abs(high - low) < 1e-10:
                        return mid
                    if previous_value * mid_value <= 0:
                        high = mid
                        current_value = mid_value
                    else:
                        low = mid
                        previous_value = mid_value
                return (low + high) / 2.0
        previous_rate, previous_value = current_rate, current_value
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
    """Investor-perspective cash flows after the opening snapshot.

    Transactions on ``period_start`` are excluded because the opening NAV already
    reflects that date's account state. Including them would double count capital.
    """
    flows: list[tuple[date, float]] = []
    if opening_nav > 0:
        flows.append((opening_date, -opening_nav))

    for txn in transactions:
        if txn.trade_date <= period_start or txn.trade_date > period_end:
            continue
        amount = external_cash_flow_amount(txn)
        if amount == 0.0:
            continue
        if txn.currency.upper() == base_currency.upper():
            rate = 1.0
        else:
            try:
                rate = float(fx_resolver(txn.currency, base_currency, txn.trade_date))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Transaction-date FX required for {txn.currency}/{base_currency} on {txn.trade_date}"
                ) from exc
        if rate <= 0:
            raise ValueError(f"Invalid FX rate for {txn.currency}/{base_currency}: {rate}")
        flows.append((txn.trade_date, -(amount * rate)))

    if terminal_nav > 0:
        flows.append((terminal_date, terminal_nav))
    return sorted(flows, key=lambda item: item[0])


def calculate_performance_returns(
    account_id: str,
    history: list[PortfolioPnLSnapshot],
    base_currency: str,
    fx_resolver: Callable[[str, str], float],
    allow_mock: bool = False,
) -> PerformanceReturns:
    transactions = get_transactions(account_id)
    coverage = load_ledger_coverage(account_id)
    ordered = _latest_daily_snapshots(history)

    period_start = date.fromisoformat(ordered[0].date) if ordered else date.today()
    period_end = date.fromisoformat(ordered[-1].date) if ordered else date.today()
    period_days = max((period_end - period_start).days, 0)
    covers_period = ledger_covers_period(coverage, period_start, period_end)

    daily_rows = _daily_investment_returns(
        ordered,
        transactions,
        base_currency,
        fx_resolver,
        ledger_complete=covers_period,
    )
    daily_return_values = [
        float(row["investment_return_percent"]) / 100.0
        for row in daily_rows[1:]
        if row.get("return_status") in {"cash_flow_adjusted", "modified_dietz", "subperiod_twr"}
    ]

    expected_intervals = max(len(ordered) - 1, 0)
    all_intervals_valid = covers_period and len(daily_return_values) == expected_intervals and expected_intervals > 0
    twr = calculate_time_weighted_return(daily_return_values) if all_intervals_valid else None

    return_statuses = {
        str(row.get("return_status"))
        for row in daily_rows[1:]
        if row.get("return_status") not in {None, "opening_observation", "withheld_incomplete_ledger"}
    }
    if not covers_period:
        return_methodology = "withheld"
    elif return_statuses == {"subperiod_twr"}:
        return_methodology = "subperiod_twr"
    elif return_statuses <= {"modified_dietz", "cash_flow_adjusted", "subperiod_twr"}:
        return_methodology = "modified_dietz"
    else:
        return_methodology = "cash_flow_adjusted" if all_intervals_valid else "withheld"

    modified_dietz = twr
    modified_dietz_annualized = None
    if modified_dietz is not None and period_days >= MIN_ANNUALIZATION_DAYS and modified_dietz > -1.0:
        modified_dietz_annualized = (1.0 + modified_dietz) ** (365.0 / period_days) - 1.0

    twr_annualized = None
    if twr is not None and period_days >= MIN_ANNUALIZATION_DAYS and twr > -1.0:
        twr_annualized = (1.0 + twr) ** (365.0 / period_days) - 1.0

    xirr = None
    if covers_period and len(ordered) >= 2:
        xirr_flows = build_xirr_cash_flows(
            transactions,
            ordered[0].net_liquidation,
            period_start,
            ordered[-1].net_liquidation,
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
        ordered,
        portfolio_twr_percent=portfolio_twr_percent,
        allow_mock=allow_mock,
    )

    cash_flow_status = "sufficient" if covers_period else "missing"
    if coverage and coverage.execution_only:
        cash_flow_status = "partial_execution_only"
    elif coverage and coverage.status == "partial":
        cash_flow_status = "partial"
    elif coverage and coverage.status == "error":
        cash_flow_status = "error"

    data_quality = {
        "cash_flow_adjustment": cash_flow_status,
        "history_observations": str(len(ordered)),
        "raw_history_observations": str(len(history)),
        "transaction_count": str(len(transactions)),
        "ledger_status": coverage.status if coverage else "missing",
        "ledger_execution_only": str(coverage.execution_only if coverage else False),
        "benchmark_series": str(benchmark_comparison.get("status", "missing")),
    }

    methodology = (
        "Daily performance uses the latest portfolio snapshot per calendar date. Interval returns without external "
        "cash flows use beginning-to-ending NAV. When external flows exist, Modified Dietz or exact subperiod linking "
        "is used instead of end-of-interval flow timing. TWR compounds valid interval returns. XIRR uses opening NAV, "
        "external contributions/distributions after the opening snapshot, and terminal NAV."
    )
    if not covers_period:
        methodology += " TWR, XIRR, and interval returns are withheld because the activity ledger does not cover the full period."
    if twr is not None and period_days < MIN_ANNUALIZATION_DAYS:
        methodology += f" Annualized TWR is withheld for periods shorter than {MIN_ANNUALIZATION_DAYS} days."
    if return_methodology == "modified_dietz":
        methodology += (
            " Interval returns with external cash flows use Modified Dietz flow weights derived from trade dates."
        )
    elif return_methodology == "subperiod_twr":
        methodology += " Interval returns with external cash flows use exact subperiod linking at flow dates."

    from app.services.analytics.calculation_run import create_calculation_run

    exclusions: list[str] = []
    if not covers_period:
        exclusions.append("ledger_incomplete")
    run = create_calculation_run(
        run_type="performance_returns",
        account_id=account_id,
        input_snapshot_ids=[f"{row.date}:{row.timestamp}" for row in ordered],
        transaction_batch_ids=[coverage.source] if coverage else [],
        exclusions=exclusions,
        coverage={
            "ledger_status": coverage.status if coverage else "missing",
            "return_methodology": return_methodology,
        },
        methodology_version=METHODOLOGY_VERSION,
    )

    return PerformanceReturns(
        time_weighted_return=portfolio_twr_percent,
        time_weighted_return_annualized=round(twr_annualized * 100.0, 4) if twr_annualized is not None else None,
        modified_dietz_return=round(modified_dietz * 100.0, 4) if modified_dietz is not None else None,
        modified_dietz_return_annualized=(
            round(modified_dietz_annualized * 100.0, 4) if modified_dietz_annualized is not None else None
        ),
        return_methodology=return_methodology,
        xirr=round(xirr * 100.0, 4) if xirr is not None else None,
        period_days=period_days,
        observation_count=len(ordered),
        daily_returns=daily_rows,
        benchmark_comparison=benchmark_comparison,
        data_quality=data_quality,
        methodology=methodology,
        calculation_run_id=run.calculation_run_id,
    )
