from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class TaxLotTransitionInput:
    lot_id: str
    symbol: str
    quantity: float
    cost_basis: float
    market_value: float
    unrealized_gain_loss: float
    holding_period_days: int
    is_wash_sale_blocked: bool = False


@dataclass(frozen=True)
class TaxTransitionRequest:
    account_type: str
    jurisdiction: str
    tax_lots: list[TaxLotTransitionInput]
    tax_budget: float | None
    available_loss_offsets: float = 0.0
    superficial_loss_blocked_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxTransitionResult:
    sell_candidates: list[str] = field(default_factory=list)
    blocked_lots: list[str] = field(default_factory=list)
    estimated_tax: float = 0.0
    transition_cost: float = 0.0
    after_tax_feasible: bool = True
    exclusions: list[str] = field(default_factory=list)


def _estimated_tax_rate(account_type: str, jurisdiction: str, holding_period_days: int) -> float:
    if jurisdiction.upper() in {"CA", "CAN", "CANADA"}:
        return 0.25
    if account_type.lower() in {"ira", "rrsp", "tfsa", "tax_deferred", "tax_free"}:
        return 0.0
    if holding_period_days >= 365:
        return 0.15
    return 0.25


def evaluate_tax_transition(request: TaxTransitionRequest) -> TaxTransitionResult:
    sell_candidates: list[str] = []
    blocked_lots: list[str] = []
    exclusions: list[str] = []
    estimated_tax = 0.0
    transition_cost = 0.0

    for lot in request.tax_lots:
        if lot.symbol.upper() in {symbol.upper() for symbol in request.superficial_loss_blocked_symbols}:
            blocked_lots.append(lot.lot_id)
            exclusions.append(f"superficial_loss_blocked:{lot.symbol}")
            continue
        if lot.is_wash_sale_blocked:
            blocked_lots.append(lot.lot_id)
            exclusions.append(f"wash_sale_blocked:{lot.lot_id}")
            continue
        if lot.unrealized_gain_loss <= 0:
            sell_candidates.append(lot.lot_id)
            continue
        rate = _estimated_tax_rate(request.account_type, request.jurisdiction, lot.holding_period_days)
        lot_tax = lot.unrealized_gain_loss * rate
        estimated_tax += lot_tax
        if request.tax_budget is not None and estimated_tax > request.tax_budget:
            blocked_lots.append(lot.lot_id)
            exclusions.append(f"tax_budget_exceeded:{lot.lot_id}")
            continue
        sell_candidates.append(lot.lot_id)

    net_tax = max(0.0, estimated_tax - request.available_loss_offsets)
    after_tax_feasible = request.tax_budget is None or net_tax <= request.tax_budget
    transition_cost = float(Decimal(str(net_tax)))

    return TaxTransitionResult(
        sell_candidates=sell_candidates,
        blocked_lots=blocked_lots,
        estimated_tax=net_tax,
        transition_cost=transition_cost,
        after_tax_feasible=after_tax_feasible,
        exclusions=exclusions,
    )
