from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
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


def lot_marginal_tax_rate(
    lot: TaxLotTransitionInput,
    *,
    account_type: str,
    jurisdiction: str,
) -> float:
    if lot.unrealized_gain_loss <= 0:
        return 0.0
    return _estimated_tax_rate(account_type, jurisdiction, lot.holding_period_days)


def build_tax_lot_transition_inputs_from_open_lots(
    open_lots: list,
    *,
    marks_by_symbol: dict[str, float],
    as_of: date,
    wash_sale_blocked_lot_ids: set[str] | None = None,
) -> list[TaxLotTransitionInput]:
    """Map TaxLot-like open lots + marks into transition inputs."""
    blocked = wash_sale_blocked_lot_ids or set()
    inputs: list[TaxLotTransitionInput] = []
    for index, lot in enumerate(open_lots):
        symbol = str(getattr(lot, "symbol", "") or "").upper()
        quantity = float(getattr(lot, "quantity", 0.0) or 0.0)
        if quantity <= 0 or not symbol:
            continue
        cost_per_share = float(getattr(lot, "cost_basis_per_share", 0.0) or 0.0)
        mark = float(marks_by_symbol.get(symbol, 0.0) or 0.0)
        if mark <= 0:
            mark = cost_per_share
        market_value = quantity * mark
        cost_basis = quantity * cost_per_share
        acquired = getattr(lot, "acquired_date", None)
        holding_days = 0
        if isinstance(acquired, date):
            holding_days = max(0, (as_of - acquired).days)
        con_id = getattr(lot, "con_id", None)
        acquired_key = acquired.isoformat() if isinstance(acquired, date) else "unknown"
        lot_id = f"{symbol}:{con_id or 'na'}:{acquired_key}:{index}"
        inputs.append(
            TaxLotTransitionInput(
                lot_id=lot_id,
                symbol=symbol,
                quantity=quantity,
                cost_basis=cost_basis,
                market_value=market_value,
                unrealized_gain_loss=market_value - cost_basis,
                holding_period_days=holding_days,
                is_wash_sale_blocked=lot_id in blocked,
            )
        )
    return inputs


def symbol_sell_tax_rate_and_capacity(
    *,
    symbol: str,
    market_value: float,
    lots: list[TaxLotTransitionInput],
    transition: TaxTransitionResult,
    account_type: str,
    jurisdiction: str,
) -> tuple[float, float]:
    """Return (sell_tax_rate_per_unit in weight space, sellable_fraction of MV)."""
    symbol_u = symbol.upper()
    symbol_lots = [lot for lot in lots if lot.symbol.upper() == symbol_u]
    if not symbol_lots or market_value <= 0:
        return 0.0, 1.0

    sellable_ids = {lot_id for lot_id in transition.sell_candidates}
    blocked_ids = {lot_id for lot_id in transition.blocked_lots}
    sellable_mv = 0.0
    blocked_mv = 0.0
    tax_numerator = 0.0
    for lot in symbol_lots:
        lot_mv = abs(lot.market_value)
        if lot.lot_id in blocked_ids or lot.lot_id not in sellable_ids:
            blocked_mv += lot_mv
            continue
        sellable_mv += lot_mv
        rate = lot_marginal_tax_rate(lot, account_type=account_type, jurisdiction=jurisdiction)
        tax_numerator += max(0.0, lot.unrealized_gain_loss) * rate

    total_lot_mv = sellable_mv + blocked_mv
    if total_lot_mv <= 0:
        return 0.0, 1.0
    sellable_fraction = sellable_mv / total_lot_mv
    rate_per_unit = tax_numerator / max(abs(market_value), 1e-6)
    return rate_per_unit, sellable_fraction


def evaluate_tax_transition(request: TaxTransitionRequest) -> TaxTransitionResult:
    sell_candidates: list[str] = []
    blocked_lots: list[str] = []
    exclusions: list[str] = []
    estimated_tax = 0.0

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
