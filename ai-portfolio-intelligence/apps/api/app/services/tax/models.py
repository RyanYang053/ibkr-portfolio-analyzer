from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal


class TaxLotMethod(str, Enum):
    FIFO = "fifo"
    LIFO = "lifo"
    HIFO = "hifo"
    SPECIFIC_ID = "specific_id"
    TAX_LOSS_HARVEST = "tax_loss_harvest"
    ACB = "acb"


@dataclass(frozen=True)
class TaxLotSnapshot:
    account_id: str
    symbol: str
    quantity: float
    cost_basis_per_share: float
    acquired_date: date
    currency: str
    con_id: int | None = None
    jurisdiction: Literal["US", "CA", "OTHER"] = "OTHER"
    method: TaxLotMethod = TaxLotMethod.FIFO


@dataclass(frozen=True)
class RealizedTaxLot:
    symbol: str
    tax_realized_gain_loss: float | None
    short_term_gain_loss: float | None
    long_term_gain_loss: float | None
    quantity_sold: float
    unmatched_sell_quantity: float = 0.0
    proceeds: float | None = None
    cost_basis: float | None = None
    holding_period_days: int = 0
    method: TaxLotMethod = TaxLotMethod.FIFO
    jurisdiction: Literal["US", "CA", "OTHER"] = "US"
    methodology_status: str = "experimental"
    wash_sale_disallowed_loss: float = 0.0


@dataclass(frozen=True)
class TaxAttributionReport:
    account_id: str
    jurisdiction: Literal["US", "CA", "OTHER"]
    method: TaxLotMethod
    methodology_status: str
    reporting_currency: str
    open_lots: list[TaxLotSnapshot]
    realized_lots: list[RealizedTaxLot]
    total_tax_realized_gain_loss: float | None
    total_short_term: float | None
    total_long_term: float | None
    unmatched_sell_quantity: float
    data_quality: dict[str, str]
    methodology: str
    period_start: date | None = None
    period_end: date | None = None
