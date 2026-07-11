from __future__ import annotations

from datetime import date
from typing import Any, Callable

from app.schemas.domain import FundamentalFieldLineage

DEBT_CONCEPT_HIERARCHY: tuple[tuple[str, ...], ...] = (
    ("LongTermDebtNoncurrent", "LongTermDebt"),
    ("LongTermDebtCurrent",),
    ("ShortTermBorrowings", "ShortTermDebtCurrent"),
    ("CommercialPaper",),
    ("FinanceLeaseLiabilityCurrent",),
    ("FinanceLeaseLiabilityNoncurrent",),
)

DEBT_CONCEPT_ALIASES: dict[str, str] = {
    "ShortTermDebt": "ShortTermDebtCurrent",
    "LongTermDebtAndCapitalLeaseObligations": "LongTermDebtNoncurrent",
}

ALL_REGISTRY_CONCEPTS: tuple[str, ...] = (
    "Revenues",
    "SalesRevenueNet",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "CommonStockholdersEquity",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "ShortTermInvestments",
    "ShortTermBorrowings",
    "ShortTermDebtCurrent",
    "LongTermDebtCurrent",
    "LongTermDebtNoncurrent",
    "CommercialPaper",
    "FinanceLeaseLiabilityCurrent",
    "FinanceLeaseLiabilityNoncurrent",
    "DilutedSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "DepreciationDepletionAndAmortization",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "NetCashProvidedByUsedInOperatingActivities",
    "IncreaseDecreaseInOperatingCapital",
    "PaymentsOfDividends",
    "InterestIncomeExpenseNet",
    "RealEstateInvestmentPropertyNet",
    "RegulatedAndUnregulatedOperatingRevenue",
    "FundsFromOperations",
    "AdjustedFundsFromOperations",
    "OccupancyRate",
    "RegulatoryAssets",
)


def resolve_nonduplicative_debt(
    latest_instant: Callable[[dict[str, Any], str, date | None], tuple[float | None, dict[str, Any] | None]],
    facts: dict[str, Any],
    *,
    as_of: date | None = None,
) -> tuple[float | None, FundamentalFieldLineage | None, list[str]]:
    """Sum nonduplicative debt concepts without double-counting parent/child pairs."""
    chosen: list[tuple[str, float, dict[str, Any]]] = []
    used_concepts: set[str] = set()
    exclusions: list[str] = []

    for group in DEBT_CONCEPT_HIERARCHY:
        for concept in group:
            if concept in used_concepts:
                continue
            value, row = latest_instant(facts, concept, as_of=as_of)
            if value is None or row is None:
                continue
            if value <= 0:
                exclusions.append(f"debt_concept_nonpositive:{concept}")
                continue
            chosen.append((concept, float(value), row))
            used_concepts.add(concept)
            for sibling in group:
                if sibling != concept:
                    used_concepts.add(sibling)
            break

    if not chosen:
        return None, None, exclusions

    total = sum(item[1] for item in chosen)
    primary = chosen[0]
    source_ids = [f"{item[0]}:{item[2].get('accn', '')}" for item in chosen]
    lineage = FundamentalFieldLineage(
        metric="total_debt",
        concept="+".join(item[0] for item in chosen),
        unit=str(primary[2].get("unit", "USD")),
        value=total,
        start_date=_parse_date(primary[2].get("start")),
        end_date=_parse_date(primary[2].get("end")),
        filed_date=_parse_date(primary[2].get("filed")),
        accepted_at=_parse_accepted(primary[2].get("accepted")),
        accession=primary[2].get("accn"),
        form=primary[2].get("form"),
        fiscal_year=primary[2].get("fy"),
        fiscal_period=primary[2].get("fp"),
        derivation="hierarchy_sum",
        source_ids=source_ids,
    )
    return total, lineage, exclusions


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_accepted(value: str | None):
    if not value:
        return None
    try:
        from datetime import datetime, timezone

        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None
