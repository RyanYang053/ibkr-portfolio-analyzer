from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.valuation.models.base import ValuationInputLineage, ValuationOutput, ValuationScenario
from app.services.valuation.models.validation import positive_decimal


@dataclass(frozen=True)
class UtilityRateBaseInputs:
    rate_base: Decimal | None
    allowed_roe: Decimal | None
    equity_capitalization: Decimal | None
    capex: Decimal | None
    debt_financing: Decimal | None
    share_count: Decimal | None
    currency: str
    as_of: date
    source_ids: list[str]


def evaluate_utility_rate_base(
    inputs: UtilityRateBaseInputs,
    scenarios: list[ValuationScenario],
) -> ValuationOutput:
    exclusions: list[str] = ["utility_valuation_model_not_validated"]
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="share_count",
    )

    positive_decimal(inputs.rate_base, "rate_base", exclusions)
    positive_decimal(inputs.allowed_roe, "allowed_roe", exclusions)
    positive_decimal(inputs.equity_capitalization, "equity_capitalization", exclusions)
    positive_decimal(inputs.capex, "capex", exclusions)
    if inputs.debt_financing is None:
        exclusions.append("debt_financing_unavailable")
    positive_decimal(inputs.share_count, "share_count", exclusions)
    if len(scenarios) < 3:
        exclusions.append("base_bull_bear_scenarios_required")

    return ValuationOutput(
        status="withheld",
        enterprise_value=None,
        equity_value=None,
        per_share_value=None,
        scenarios=[],
        exclusions=exclusions,
        lineage=lineage,
    )
