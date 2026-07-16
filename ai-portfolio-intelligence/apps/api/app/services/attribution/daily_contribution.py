from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyContribution:
    contribution_date: date
    security_contribution: float
    income_contribution: float
    fx_contribution: float
    fee_contribution: float
    tax_contribution: float
    allocation_effect: float
    selection_effect: float
    interaction_effect: float
    portfolio_return: float | None = None
    benchmark_return: float | None = None
    corp_action_contribution: float = 0.0
    cash_contribution: float = 0.0

    @property
    def total_return_contribution(self) -> float:
        return (
            self.security_contribution
            + self.income_contribution
            + self.fx_contribution
            + self.fee_contribution
            + self.tax_contribution
            + self.corp_action_contribution
        )

    @property
    def total_attribution_effect(self) -> float:
        return self.allocation_effect + self.selection_effect + self.interaction_effect


def build_daily_contribution(
    *,
    contribution_date: date,
    security_return: float,
    portfolio_weight: float,
    income_return: float = 0.0,
    fx_return: float = 0.0,
    fee_return: float = 0.0,
    tax_return: float = 0.0,
    corp_action_return: float = 0.0,
    portfolio_sector_weight: float,
    benchmark_sector_weight: float,
    portfolio_sector_return: float,
    benchmark_sector_return: float,
    portfolio_return: float | None = None,
    benchmark_return: float | None = None,
) -> DailyContribution:
    security_contribution = portfolio_weight * security_return
    income_contribution = portfolio_weight * income_return
    fx_contribution = portfolio_weight * fx_return
    fee_contribution = portfolio_weight * fee_return
    tax_contribution = portfolio_weight * tax_return
    corp_action_contribution = portfolio_weight * corp_action_return

    allocation = (portfolio_sector_weight - benchmark_sector_weight) * benchmark_sector_return
    selection = benchmark_sector_weight * (portfolio_sector_return - benchmark_sector_return)
    interaction = (portfolio_sector_weight - benchmark_sector_weight) * (
        portfolio_sector_return - benchmark_sector_return
    )

    return DailyContribution(
        contribution_date=contribution_date,
        security_contribution=security_contribution,
        income_contribution=income_contribution,
        fx_contribution=fx_contribution,
        fee_contribution=fee_contribution,
        tax_contribution=tax_contribution,
        corp_action_contribution=corp_action_contribution,
        allocation_effect=allocation,
        selection_effect=selection,
        interaction_effect=interaction,
        portfolio_return=portfolio_return,
        benchmark_return=benchmark_return,
    )
