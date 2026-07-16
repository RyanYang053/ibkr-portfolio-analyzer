from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.schemas.domain import Position
from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of
from app.services.attribution.daily_contribution import DailyContribution
from app.services.attribution.engine import SECTOR_BENCHMARK_ETF
from app.services.market_data.exchange_calendar import is_us_equity_trading_day, previous_trading_session
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

DAILY_ATTRIBUTION_STATUS = "experimental_static_weight_daily_attribution"
HOLDINGS_DAILY_ATTRIBUTION_STATUS = "ledger_backed_daily_holdings_attribution"


@dataclass(frozen=True)
class DailySecurityInput:
    date: date
    instrument_key: str
    sector: str
    beginning_weight: float
    total_return: float
    income_return: float = 0.0
    fx_return: float = 0.0
    fee_return: float = 0.0
    tax_return: float = 0.0


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


def _instrument_key(symbol: str, con_id: int | None) -> str:
    if con_id is None:
        return symbol.upper()
    return f"{symbol.upper()}:{con_id}"


def _sector_for_symbol(symbol: str, positions: list[Position], fallback: str = "Unknown") -> str:
    for position in positions:
        if position.symbol.upper() == symbol.upper():
            return position.sector or fallback
    return fallback


def build_daily_security_inputs_from_history(
    history: list[PortfolioPnLSnapshot],
    *,
    period_start: date,
    period_end: date,
    positions: list[Position],
) -> list[DailySecurityInput]:
    """Derive beginning-weight security returns from consecutive PnL snapshots."""
    ordered = sorted(
        (
            item
            for item in history
            if period_start <= date.fromisoformat(item.date) <= period_end
        ),
        key=lambda item: (item.date, item.timestamp),
    )
    # Keep latest snapshot per calendar date.
    by_date: dict[date, PortfolioPnLSnapshot] = {}
    for snapshot in ordered:
        by_date[date.fromisoformat(snapshot.date)] = snapshot

    dates = sorted(by_date)
    inputs: list[DailySecurityInput] = []
    for previous_date, current_date in zip(dates, dates[1:], strict=False):
        previous = by_date[previous_date]
        current = by_date[current_date]
        beginning_total = sum(max(float(row.market_value), 0.0) for row in previous.positions)
        if beginning_total <= 0:
            continue
        current_by_key = {
            _instrument_key(row.symbol, row.con_id): row
            for row in current.positions
        }
        for prior in previous.positions:
            beginning_value = float(prior.market_value)
            if beginning_value <= 0 or prior.market_price <= 0:
                continue
            key = _instrument_key(prior.symbol, prior.con_id)
            current_row = current_by_key.get(key)
            if current_row is None or current_row.market_price <= 0:
                continue
            total_return = (float(current_row.market_price) / float(prior.market_price)) - 1.0
            inputs.append(
                DailySecurityInput(
                    date=current_date,
                    instrument_key=key,
                    sector=_sector_for_symbol(prior.symbol, positions),
                    beginning_weight=beginning_value / beginning_total,
                    total_return=total_return,
                )
            )
    return inputs


def build_daily_security_inputs_from_daily_positions(
    account_id: str,
    *,
    period_start: date,
    period_end: date,
    positions: list[Position],
) -> list[DailySecurityInput]:
    from app.db.daily_position_repo import read_daily_positions

    days = trading_days_in_range(period_start, period_end)
    if len(days) < 2:
        return []

    by_date: dict[date, list[dict]] = {}
    for day in days:
        try:
            rows = read_daily_positions(account_id, day)
        except Exception:
            rows = []
        if rows:
            by_date[day] = rows

    dated = sorted(by_date)
    inputs: list[DailySecurityInput] = []
    for previous_date, current_date in zip(dated, dated[1:], strict=False):
        previous_rows = by_date[previous_date]
        current_rows = by_date[current_date]
        beginning_total = 0.0
        for row in previous_rows:
            value = float(row.get("base_market_value") or row.get("market_value") or 0.0)
            if value > 0:
                beginning_total += value
        if beginning_total <= 0:
            continue
        current_by_key = {
            _instrument_key(str(row.get("symbol", "")), row.get("con_id")): row
            for row in current_rows
        }
        for prior in previous_rows:
            beginning_value = float(prior.get("base_market_value") or prior.get("market_value") or 0.0)
            prior_price = float(prior.get("market_price") or 0.0)
            if beginning_value <= 0 or prior_price <= 0:
                continue
            key = _instrument_key(str(prior.get("symbol", "")), prior.get("con_id"))
            current_row = current_by_key.get(key)
            if current_row is None:
                continue
            current_price = float(current_row.get("market_price") or 0.0)
            if current_price <= 0:
                continue
            sector = str(prior.get("sector") or _sector_for_symbol(str(prior.get("symbol", "")), positions))
            inputs.append(
                DailySecurityInput(
                    date=current_date,
                    instrument_key=key,
                    sector=sector,
                    beginning_weight=beginning_value / beginning_total,
                    total_return=(current_price / prior_price) - 1.0,
                )
            )
    return inputs


def _sector_portfolio_return(
    security_rows: list[DailySecurityInput],
    sector: str,
) -> float | None:
    sector_rows = [row for row in security_rows if row.sector == sector]
    sector_beginning_weight = sum(row.beginning_weight for row in sector_rows)
    if sector_beginning_weight <= 0:
        return None
    return (
        sum(row.beginning_weight * row.total_return for row in sector_rows)
        / sector_beginning_weight
    )


def build_daily_attribution_contributions(
    *,
    positions: list[Position],
    period_start: date,
    period_end: date,
    portfolio_sector_weights: dict[str, float],
    allow_mock: bool,
    history: list[PortfolioPnLSnapshot] | None = None,
    benchmark_id: str = "SPY",
    account_id: str | None = None,
    security_inputs: list[DailySecurityInput] | None = None,
) -> tuple[list[DailyContribution], str]:
    """Build daily Brinson contributions.

    Prefers holdings-based DailySecurityInput rows. Falls back to experimental
    static sector-weight attribution only when security-level inputs are absent.
    """
    benchmark_sector_weights = benchmark_sector_weights_as_of(
        period_start,
        allow_mock=allow_mock,
        benchmark_id=benchmark_id,
    )
    if not benchmark_sector_weights:
        return [], DAILY_ATTRIBUTION_STATUS

    resolved_inputs = list(security_inputs or [])
    if not resolved_inputs and account_id:
        resolved_inputs = build_daily_security_inputs_from_daily_positions(
            account_id,
            period_start=period_start,
            period_end=period_end,
            positions=positions,
        )
    if not resolved_inputs and history:
        resolved_inputs = build_daily_security_inputs_from_history(
            history,
            period_start=period_start,
            period_end=period_end,
            positions=positions,
        )

    if resolved_inputs:
        return (
            _build_holdings_based_contributions(
                security_inputs=resolved_inputs,
                portfolio_sector_weights=portfolio_sector_weights,
                benchmark_sector_weights=benchmark_sector_weights,
                allow_mock=allow_mock,
                period_start=period_start,
                period_end=period_end,
            ),
            HOLDINGS_DAILY_ATTRIBUTION_STATUS,
        )

    return (
        _build_static_weight_contributions(
            positions=positions,
            period_start=period_start,
            period_end=period_end,
            portfolio_sector_weights=portfolio_sector_weights,
            benchmark_sector_weights=benchmark_sector_weights,
            allow_mock=allow_mock,
            history=history,
        ),
        DAILY_ATTRIBUTION_STATUS,
    )


def _build_holdings_based_contributions(
    *,
    security_inputs: list[DailySecurityInput],
    portfolio_sector_weights: dict[str, float],
    benchmark_sector_weights: dict[str, float],
    allow_mock: bool,
    period_start: date,
    period_end: date,
) -> list[DailyContribution]:
    by_day: dict[date, list[DailySecurityInput]] = {}
    for row in security_inputs:
        if period_start <= row.date <= period_end:
            by_day.setdefault(row.date, []).append(row)

    sectors = sorted(set(portfolio_sector_weights) | set(benchmark_sector_weights))
    contributions: list[DailyContribution] = []
    for day in trading_days_in_range(period_start, period_end):
        day_rows = by_day.get(day, [])
        if not day_rows:
            continue
        portfolio_daily = sum(row.beginning_weight * row.total_return for row in day_rows)
        income_daily = sum(row.beginning_weight * row.income_return for row in day_rows)
        fx_daily = sum(row.beginning_weight * row.fx_return for row in day_rows)
        fee_daily = sum(row.beginning_weight * row.fee_return for row in day_rows)
        tax_daily = sum(row.beginning_weight * row.tax_return for row in day_rows)
        benchmark_daily = _etf_daily_return("SPY", day, allow_mock=allow_mock) or 0.0

        allocation = 0.0
        selection = 0.0
        interaction = 0.0
        for sector in sectors:
            etf = SECTOR_BENCHMARK_ETF.get(sector, "SPY")
            sector_benchmark_daily = _etf_daily_return(etf, day, allow_mock=allow_mock)
            if sector_benchmark_daily is None:
                continue
            weight_p = sum(row.beginning_weight for row in day_rows if row.sector == sector)
            if weight_p <= 0:
                weight_p = portfolio_sector_weights.get(sector, 0.0)
            weight_b = benchmark_sector_weights.get(sector, 0.0)
            sector_portfolio_daily = _sector_portfolio_return(day_rows, sector)
            if sector_portfolio_daily is None:
                continue
            allocation += (weight_p - weight_b) * sector_benchmark_daily
            selection += weight_b * (sector_portfolio_daily - sector_benchmark_daily)
            interaction += (weight_p - weight_b) * (sector_portfolio_daily - sector_benchmark_daily)

        contributions.append(
            DailyContribution(
                contribution_date=day,
                security_contribution=portfolio_daily,
                income_contribution=income_daily,
                fx_contribution=fx_daily,
                fee_contribution=fee_daily,
                tax_contribution=tax_daily,
                allocation_effect=allocation,
                selection_effect=selection,
                interaction_effect=interaction,
                portfolio_return=portfolio_daily,
                benchmark_return=benchmark_daily,
            )
        )
    return contributions


def _build_static_weight_contributions(
    *,
    positions: list[Position],
    period_start: date,
    period_end: date,
    portfolio_sector_weights: dict[str, float],
    benchmark_sector_weights: dict[str, float],
    allow_mock: bool,
    history: list[PortfolioPnLSnapshot] | None,
) -> list[DailyContribution]:
    _ = positions
    portfolio_returns = _daily_returns_from_history(history or [], period_start, period_end)
    sectors = sorted(set(portfolio_sector_weights) | set(benchmark_sector_weights))
    total_portfolio_weight = sum(portfolio_sector_weights.values()) or 1.0
    contributions: list[DailyContribution] = []

    for day in trading_days_in_range(period_start, period_end):
        portfolio_daily = portfolio_returns.get(day)
        if portfolio_daily is None:
            continue

        benchmark_daily = _etf_daily_return("SPY", day, allow_mock=allow_mock) or 0.0
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
            if weight_p > 0:
                sector_portfolio_daily = portfolio_daily * (weight_p / total_portfolio_weight)
            else:
                continue
            allocation += (weight_p - weight_b) * sector_benchmark_daily
            selection += weight_b * (sector_portfolio_daily - sector_benchmark_daily)
            interaction += (weight_p - weight_b) * (sector_portfolio_daily - sector_benchmark_daily)

        contributions.append(
            DailyContribution(
                contribution_date=day,
                security_contribution=portfolio_daily,
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
