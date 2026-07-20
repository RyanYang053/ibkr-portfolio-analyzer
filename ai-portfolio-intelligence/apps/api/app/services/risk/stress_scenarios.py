"""Internal risk stress scenario helpers (not broker margin)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class StressScenarioResult:
    name: str
    estimated_stress_loss: Decimal
    estimated_concentration_exposure: Decimal
    estimated_option_assignment_exposure: Decimal
    estimated_liquidity_requirement: Decimal
    label: str = "internal_scenario_estimate"


def simple_stress_loss(
    *,
    net_liquidation: Decimal,
    shock_fraction: Decimal = Decimal("0.10"),
    concentration_fraction: Decimal = Decimal("0"),
    option_assignment_exposure: Decimal = Decimal("0"),
) -> StressScenarioResult:
    loss = abs(net_liquidation) * shock_fraction
    concentration = abs(net_liquidation) * concentration_fraction
    return StressScenarioResult(
        name="uniform_price_shock",
        estimated_stress_loss=loss,
        estimated_concentration_exposure=concentration,
        estimated_option_assignment_exposure=option_assignment_exposure,
        estimated_liquidity_requirement=loss + concentration + option_assignment_exposure,
    )
