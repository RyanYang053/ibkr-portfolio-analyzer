from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.db.option_contract_repo import OptionContractNotFoundError, require_contract
from app.schemas.domain import Position


@dataclass(frozen=True)
class PortfolioGreeksSummary:
    delta: float
    gamma: float
    vega: float
    theta: float
    expiry_concentration: dict[str, float]
    assignment_exposure: float
    uncovered_notional: float
    margin_stress: float


def _fx_to_base(position: Position, base_currency: str) -> float:
    if position.currency.upper() == base_currency.upper():
        return 1.0
    from app.services.broker.ibkr_readonly import get_exchange_rate

    return float(get_exchange_rate(position.currency, base_currency))


def compute_portfolio_greeks(
    positions: list[Position],
    *,
    base_currency: str = "USD",
) -> tuple[PortfolioGreeksSummary | None, list[str]]:
    exclusions: list[str] = []
    delta = 0.0
    gamma = 0.0
    vega = 0.0
    theta = 0.0
    expiry_notional: dict[str, float] = defaultdict(float)
    assignment_exposure = 0.0
    uncovered_notional = 0.0
    margin_stress = 0.0
    option_positions = [position for position in positions if position.asset_class in {"OPT", "FOP"}]
    if not option_positions:
        return None, exclusions

    stock_by_symbol = {
        position.symbol.upper(): position
        for position in positions
        if position.asset_class not in {"OPT", "FOP"} and position.market_price > 0
    }

    for position in option_positions:
        try:
            contract = require_contract(position.con_id)
        except OptionContractNotFoundError:
            exclusions.append(f"{position.symbol}:contract_master_missing")
            continue

        fx_rate = _fx_to_base(position, base_currency)
        qty = float(position.quantity)
        multiplier = float(position.multiplier or contract.multiplier or 100.0)
        underlying = stock_by_symbol.get(contract.symbol.upper())
        underlying_spot = underlying.market_price if underlying else 0.0

        if contract.delta is not None:
            delta += qty * multiplier * contract.delta * underlying_spot * fx_rate
        if contract.gamma is not None and underlying_spot > 0:
            gamma += qty * multiplier * contract.gamma * underlying_spot * fx_rate
        if contract.vega is not None:
            vega += qty * multiplier * contract.vega * fx_rate
        if contract.theta is not None:
            theta += qty * multiplier * contract.theta * fx_rate

        notional = abs(qty * multiplier * contract.strike * fx_rate)
        expiry_notional[contract.expiration.isoformat()] += notional

        if qty < 0:
            assignment_exposure += notional
            uncovered = notional
            if contract.right.upper() == "C" and underlying is not None:
                covered = max(0.0, float(underlying.quantity)) * underlying_spot * fx_rate
                uncovered = max(0.0, notional - covered)
            uncovered_notional += uncovered
            margin_stress += uncovered * 0.20

    total_expiry = sum(expiry_notional.values()) or 1.0
    expiry_concentration = {
        expiry: round(value / total_expiry * 100.0, 2)
        for expiry, value in sorted(expiry_notional.items())
    }

    return (
        PortfolioGreeksSummary(
            delta=round(delta, 2),
            gamma=round(gamma, 4),
            vega=round(vega, 2),
            theta=round(theta, 2),
            expiry_concentration=expiry_concentration,
            assignment_exposure=round(assignment_exposure, 2),
            uncovered_notional=round(uncovered_notional, 2),
            margin_stress=round(margin_stress, 2),
        ),
        exclusions,
    )


def portfolio_greeks_as_dict(summary: PortfolioGreeksSummary | None) -> dict[str, Any]:
    if summary is None:
        return {}
    return {
        "portfolio_delta": summary.delta,
        "portfolio_gamma": summary.gamma,
        "portfolio_vega": summary.vega,
        "portfolio_theta": summary.theta,
        "expiry_concentration": summary.expiry_concentration,
        "assignment_exposure": summary.assignment_exposure,
        "uncovered_notional": summary.uncovered_notional,
        "margin_stress": summary.margin_stress,
    }
