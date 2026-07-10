from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.valuation.models.base import ValuationInputLineage, ValuationOutput, ValuationScenario
from app.services.valuation.models.validation import positive_decimal


@dataclass(frozen=True)
class ReitNavAffoInputs:
    affo_per_share: Decimal | None
    ffo_per_share: Decimal | None
    net_debt: Decimal | None
    share_count: Decimal | None
    justified_affo_multiple: Decimal | None
    currency: str
    as_of: date
    source_ids: list[str]


def evaluate_reit_nav_affo(inputs: ReitNavAffoInputs, scenarios: list[ValuationScenario]) -> ValuationOutput:
    exclusions: list[str] = ["reit_valuation_model_not_validated"]
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="share_count",
    )

    if inputs.affo_per_share is None and inputs.ffo_per_share is None:
        exclusions.append("affo_or_ffo_per_share_unavailable")
    if inputs.net_debt is None:
        exclusions.append("net_debt_unavailable")
    positive_decimal(inputs.share_count, "share_count", exclusions)
    positive_decimal(inputs.justified_affo_multiple, "justified_affo_multiple", exclusions)
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
