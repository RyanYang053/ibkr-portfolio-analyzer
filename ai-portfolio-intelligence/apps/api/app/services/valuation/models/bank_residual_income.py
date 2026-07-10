from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.valuation.models.base import ValuationInputLineage, ValuationOutput, ValuationScenario
from app.services.valuation.models.validation import positive_decimal


@dataclass(frozen=True)
class BankResidualIncomeInputs:
    tangible_common_equity: Decimal | None
    tangible_book_per_share: Decimal | None
    normalized_roe: Decimal | None
    cost_of_equity: Decimal | None
    retention_ratio: Decimal | None
    share_count: Decimal | None
    currency: str
    as_of: date
    source_ids: list[str]


def evaluate_bank_residual_income(
    inputs: BankResidualIncomeInputs,
    scenarios: list[ValuationScenario],
) -> ValuationOutput:
    exclusions: list[str] = ["bank_valuation_model_not_validated"]
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="share_count",
    )

    positive_decimal(inputs.tangible_common_equity, "tangible_common_equity", exclusions)
    positive_decimal(inputs.tangible_book_per_share, "tangible_book_per_share", exclusions)
    positive_decimal(inputs.normalized_roe, "normalized_roe", exclusions)
    positive_decimal(inputs.cost_of_equity, "cost_of_equity", exclusions)
    if inputs.retention_ratio is None:
        exclusions.append("retention_ratio_unavailable")
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
