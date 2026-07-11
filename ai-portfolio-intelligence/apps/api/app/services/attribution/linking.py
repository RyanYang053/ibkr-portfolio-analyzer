from __future__ import annotations

from dataclasses import dataclass

from app.services.attribution.daily_contribution import DailyContribution


@dataclass(frozen=True)
class LinkedAttribution:
    linked_allocation: float
    linked_selection: float
    linked_interaction: float
    linked_active_return: float
    portfolio_compound_return: float
    benchmark_compound_return: float
    reconciliation_gap: float
    within_tolerance: bool


def _compound(returns: list[float]) -> float:
    compounded = 1.0
    for value in returns:
        compounded *= 1.0 + value
    return compounded - 1.0


def geometric_link_attribution_effects(
    daily_contributions: list[DailyContribution],
    *,
    tolerance: float = 1e-4,
) -> LinkedAttribution:
    if not daily_contributions:
        return LinkedAttribution(
            linked_allocation=0.0,
            linked_selection=0.0,
            linked_interaction=0.0,
            linked_active_return=0.0,
            portfolio_compound_return=0.0,
            benchmark_compound_return=0.0,
            reconciliation_gap=0.0,
            within_tolerance=True,
        )

    portfolio_returns = [
        item.portfolio_return
        for item in daily_contributions
        if item.portfolio_return is not None
    ]
    benchmark_returns = [
        item.benchmark_return
        for item in daily_contributions
        if item.benchmark_return is not None
    ]
    portfolio_compound = _compound(portfolio_returns) if portfolio_returns else _compound(
        [item.total_return_contribution for item in daily_contributions]
    )
    benchmark_compound = _compound(benchmark_returns) if benchmark_returns else 0.0

    linked_allocation = 0.0
    linked_selection = 0.0
    linked_interaction = 0.0
    cumulative_portfolio = 1.0
    cumulative_benchmark = 1.0

    for item in daily_contributions:
        day_portfolio = item.portfolio_return if item.portfolio_return is not None else item.total_return_contribution
        day_benchmark = item.benchmark_return if item.benchmark_return is not None else 0.0
        linked_allocation += item.allocation_effect * cumulative_benchmark
        linked_selection += item.selection_effect * cumulative_benchmark
        linked_interaction += item.interaction_effect * cumulative_benchmark
        cumulative_portfolio *= 1.0 + day_portfolio
        cumulative_benchmark *= 1.0 + day_benchmark

    linked_active = linked_allocation + linked_selection + linked_interaction
    expected_active = portfolio_compound - benchmark_compound
    gap = linked_active - expected_active
    within_tolerance = abs(gap) <= tolerance

    return LinkedAttribution(
        linked_allocation=linked_allocation,
        linked_selection=linked_selection,
        linked_interaction=linked_interaction,
        linked_active_return=linked_active,
        portfolio_compound_return=portfolio_compound,
        benchmark_compound_return=benchmark_compound,
        reconciliation_gap=gap,
        within_tolerance=within_tolerance,
    )


def active_return_reconciles(
    daily_contributions: list[DailyContribution],
    *,
    tolerance: float = 1e-4,
) -> tuple[bool, float]:
    linked = geometric_link_attribution_effects(daily_contributions, tolerance=tolerance)
    return linked.within_tolerance, linked.reconciliation_gap
