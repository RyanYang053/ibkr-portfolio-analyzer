from __future__ import annotations

from datetime import date, timedelta

from app.schemas.domain import Position
from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of
from app.services.attribution.daily_contribution import DailyContribution
from app.services.attribution.engine import SECTOR_BENCHMARK_ETF
from app.services.market_data.exchange_calendar import is_us_equity_trading_day, previous_trading_session
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot


def trading_days_in_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days: list[date] = []
    current = start
    while current <= end:
        if is_us_equity_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _etf_close_on(etf: str, day: date, *, allow_mock: bool) -> float | None:
    from app.services.attribution.brinson_ledger import _price_on_or_before

    return _price_on_or_before(etf, day, allow_mock=allow_mock)


def _etf_daily_return(etf: str, day: date, *, allow_mock: bool) -> float | None:
    prior = previous_trading_session(day)
    start_close = _etf_close_on(etf, prior, allow_mock=allow_mock)
    end_close = _etf_close_on(etf, day, allow_mock=allow_mock)
    if start_close is None or end_close is None or start_close <= 0:
        return None
    return (end_close / start_close) - 1.0


def _daily_returns_from_history(
    history: list[PortfolioPnLSnapshot],
    period_start: date,
    period_end: date,
) -> dict[date, float]:
    ordered = sorted(
        (
            item
            for item in history
            if period_start <= date.fromisoformat(item.date) <= period_end
        ),
        key=lambda item: (item.date, item.timestamp),
    )
    returns: dict[date, float] = {}
    for previous, current in zip(ordered, ordered[1:], strict=False):
        day = date.fromisoformat(current.date)
        if current.investment_return_percent is not None:
            returns[day] = float(current.investment_return_percent) / 100.0
            continue
        if previous.net_liquidation > 0:
            returns[day] = (current.net_liquidation - previous.net_liquidation) / previous.net_liquidation
    return returns


def build_daily_attribution_contributions(
    *,
    positions: list[Position],
    period_start: date,
    period_end: date,
    portfolio_sector_weights: dict[str, float],
    allow_mock: bool,
    history: list[PortfolioPnLSnapshot] | None = None,
    benchmark_id: str = "SPY",
) -> list[DailyContribution]:
    _ = positions
    benchmark_sector_weights = benchmark_sector_weights_as_of(period_start, allow_mock=allow_mock, benchmark_id=benchmark_id)
    if not benchmark_sector_weights:
        return []

    portfolio_returns = _daily_returns_from_history(history or [], period_start, period_end)
    sectors = sorted(set(portfolio_sector_weights) | set(benchmark_sector_weights))
    total_portfolio_weight = sum(portfolio_sector_weights.values()) or 1.0
    contributions: list[DailyContribution] = []

    for day in trading_days_in_range(period_start, period_end):
        benchmark_daily = _etf_daily_return("SPY", day, allow_mock=allow_mock) or 0.0
        portfolio_daily = portfolio_returns.get(day)

        allocation = 0.0
        selection = 0.0
        interaction = 0.0
        for sector in sectors:
            etf = SECTOR_BENCHMARK_ETF.get(sector, "SPY")
            sector_benchmark_daily = _etf_daily_return(etf, day, allow_mock=allow_mock)
            if sector_benchmark_daily is None:
                continue
            weight_p = portfolio_sector_weights.get(sector, 0.0)
            weight_b = benchmark_sector_weights.get(sector, 0.0)
            if portfolio_daily is not None and weight_p > 0:
                sector_portfolio_daily = portfolio_daily * (weight_p / total_portfolio_weight)
            else:
                sector_portfolio_daily = sector_benchmark_daily
            allocation += (weight_p - weight_b) * sector_benchmark_daily
            selection += weight_b * (sector_portfolio_daily - sector_benchmark_daily)
            interaction += (weight_p - weight_b) * (sector_portfolio_daily - sector_benchmark_daily)

        contributions.append(
            DailyContribution(
                contribution_date=day,
                security_contribution=portfolio_daily or 0.0,
                income_contribution=0.0,
                fx_contribution=0.0,
                fee_contribution=0.0,
                tax_contribution=0.0,
                allocation_effect=allocation,
                selection_effect=selection,
                interaction_effect=interaction,
                portfolio_return=portfolio_daily,
                benchmark_return=benchmark_daily,
            )
        )

    return contributions
