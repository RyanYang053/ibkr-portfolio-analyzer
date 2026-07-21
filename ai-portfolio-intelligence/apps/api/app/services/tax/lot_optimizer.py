"""Tax-lot selection helpers — never generate broker orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

LotMethodName = Literal["fifo", "lifo", "hifo", "specific_id", "tax_loss_harvest"]


@dataclass(frozen=True)
class OpenLotView:
    symbol: str
    quantity: float
    cost_basis_per_share: float
    acquired_date: date | str | None = None
    lot_id: str | None = None
    mark_price: float | None = None


@dataclass(frozen=True)
class LotPick:
    symbol: str
    quantity: float
    cost_basis_per_share: float
    acquired_date: date | str | None
    estimated_gain_loss: float
    lot_id: str | None = None
    method: str = "fifo"


def _as_date_key(value: date | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _estimated_gl(lot: OpenLotView, qty: float, mark_price: float) -> float:
    return round(qty * (mark_price - float(lot.cost_basis_per_share)), 6)


def _sort_lots(open_lots: list[OpenLotView], method: LotMethodName) -> list[OpenLotView]:
    if method == "fifo":
        return sorted(open_lots, key=lambda lot: (_as_date_key(lot.acquired_date), lot.cost_basis_per_share))
    if method == "lifo":
        return sorted(
            open_lots,
            key=lambda lot: (_as_date_key(lot.acquired_date), lot.cost_basis_per_share),
            reverse=True,
        )
    if method == "hifo":
        return sorted(
            open_lots,
            key=lambda lot: (-float(lot.cost_basis_per_share), _as_date_key(lot.acquired_date)),
        )
    if method == "tax_loss_harvest":
        # Prefer largest unrealized losses first when mark is known; else highest cost.
        return sorted(
            open_lots,
            key=lambda lot: (
                float(lot.cost_basis_per_share) - float(lot.mark_price or 0.0),
                -float(lot.cost_basis_per_share),
                _as_date_key(lot.acquired_date),
            ),
            reverse=True,
        )
    # specific_id — preserve caller order (explicit identification)
    return list(open_lots)


def select_lots_for_sale(
    open_lots: list[OpenLotView] | list[dict[str, Any]],
    quantity: float,
    method: LotMethodName = "fifo",
    mark_price: float | None = None,
) -> list[LotPick]:
    """Return ordered lot picks covering `quantity` with estimated gain/loss."""
    if quantity <= 0:
        return []
    normalized: list[OpenLotView] = []
    for raw in open_lots:
        if isinstance(raw, OpenLotView):
            lot = raw
        else:
            lot = OpenLotView(
                symbol=str(raw.get("symbol") or "").upper(),
                quantity=float(raw.get("quantity") or 0),
                cost_basis_per_share=float(raw.get("cost_basis_per_share") or 0),
                acquired_date=raw.get("acquired_date"),
                lot_id=str(raw.get("lot_id") or raw.get("id") or "") or None,
                mark_price=(
                    float(raw["mark_price"])
                    if raw.get("mark_price") is not None
                    else mark_price
                ),
            )
        if lot.quantity > 1e-12:
            if mark_price is not None and lot.mark_price is None:
                lot = OpenLotView(
                    symbol=lot.symbol,
                    quantity=lot.quantity,
                    cost_basis_per_share=lot.cost_basis_per_share,
                    acquired_date=lot.acquired_date,
                    lot_id=lot.lot_id,
                    mark_price=mark_price,
                )
            normalized.append(lot)

    ordered = _sort_lots(normalized, method)
    remaining = float(quantity)
    picks: list[LotPick] = []
    for lot in ordered:
        if remaining <= 1e-12:
            break
        take = min(remaining, float(lot.quantity))
        mark = float(lot.mark_price if lot.mark_price is not None else mark_price or lot.cost_basis_per_share)
        picks.append(
            LotPick(
                symbol=lot.symbol,
                quantity=round(take, 6),
                cost_basis_per_share=float(lot.cost_basis_per_share),
                acquired_date=lot.acquired_date,
                estimated_gain_loss=_estimated_gl(lot, take, mark),
                lot_id=lot.lot_id,
                method=method,
            )
        )
        remaining -= take
    return picks


def optimize_tax_aware_sales(
    positions_with_lots: list[dict[str, Any]],
    target_weights: dict[str, float],
    *,
    current_weights: dict[str, float] | None = None,
    method: LotMethodName = "tax_loss_harvest",
    portfolio_value: float | None = None,
    short_term_rate: float = 0.37,
    long_term_rate: float = 0.20,
) -> dict[str, Any]:
    """Build a provisional tax-aware sale plan. Never emits broker orders."""
    current = {str(k).upper(): float(v) for k, v in (current_weights or {}).items()}
    targets = {str(k).upper(): float(v) for k, v in target_weights.items()}
    symbols = sorted(set(current) | set(targets) | {str(p.get("symbol") or "").upper() for p in positions_with_lots})
    symbols = [s for s in symbols if s and s != "CASH"]

    lot_index: dict[str, list[dict[str, Any]]] = {}
    for position in positions_with_lots:
        symbol = str(position.get("symbol") or "").upper()
        if not symbol:
            continue
        lots = list(position.get("lots") or [])
        mark = position.get("mark_price")
        for lot in lots:
            row = dict(lot)
            row.setdefault("symbol", symbol)
            if mark is not None and row.get("mark_price") is None:
                row["mark_price"] = mark
            lot_index.setdefault(symbol, []).append(row)

    nav = float(portfolio_value) if portfolio_value and portfolio_value > 0 else 100.0
    picks: list[dict[str, Any]] = []
    provisional_tax = 0.0
    for symbol in symbols:
        delta_w = targets.get(symbol, 0.0) - current.get(symbol, 0.0)
        if delta_w >= -1e-9:
            continue
        # Weight percent → notional quantity proxy using mark when available.
        mark = None
        if lot_index.get(symbol):
            mark = next(
                (
                    float(lot["mark_price"])
                    for lot in lot_index[symbol]
                    if lot.get("mark_price") is not None
                ),
                None,
            )
        weight_cut = abs(delta_w)
        if mark and mark > 0:
            qty = (weight_cut / 100.0) * nav / mark
        else:
            qty = sum(float(lot.get("quantity") or 0) for lot in lot_index.get(symbol, [])) * (weight_cut / max(current.get(symbol, weight_cut), 1e-9))
        selected = select_lots_for_sale(lot_index.get(symbol, []), qty, method=method, mark_price=mark)
        for pick in selected:
            gl = pick.estimated_gain_loss
            # Holding-period heuristic: unknown → blend short/long rates conservatively.
            rate = short_term_rate if gl > 0 else (short_term_rate if gl < 0 else 0.0)
            if gl < 0:
                rate = short_term_rate  # harvest benefit provisional
            tax = gl * rate if gl > 0 else gl * rate
            provisional_tax += tax
            picks.append(
                {
                    "symbol": pick.symbol,
                    "quantity": pick.quantity,
                    "cost_basis_per_share": pick.cost_basis_per_share,
                    "acquired_date": (
                        pick.acquired_date.isoformat()
                        if isinstance(pick.acquired_date, date)
                        else pick.acquired_date
                    ),
                    "estimated_gain_loss": pick.estimated_gain_loss,
                    "lot_id": pick.lot_id,
                    "method": pick.method,
                    "provisional_tax": round(tax, 4),
                }
            )

    return {
        "method": method,
        "lot_picks": picks,
        "provisional_tax": round(provisional_tax, 4),
        "provisional_expected_tax": round(provisional_tax, 4),
        "order_generated": False,
        "orders": [],
        "methodology_id": "tax_lot_methodology",
        "note": "Tax-aware lot plan is a worksheet estimate; no broker orders are generated.",
    }
