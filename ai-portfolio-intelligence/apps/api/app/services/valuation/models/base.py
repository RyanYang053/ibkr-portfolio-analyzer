from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class ValuationInputLineage:
    source_ids: list[str]
    as_of: date
    currency: str
    share_count_source: str | None


@dataclass(frozen=True)
class ValuationScenario:
    name: str
    assumptions: dict[str, Decimal]


@dataclass(frozen=True)
class ValuationOutput:
    status: Literal["available", "provisional", "withheld"]
    enterprise_value: Decimal | None
    equity_value: Decimal | None
    per_share_value: Decimal | None
    scenarios: list[dict]
    exclusions: list[str]
    lineage: ValuationInputLineage
