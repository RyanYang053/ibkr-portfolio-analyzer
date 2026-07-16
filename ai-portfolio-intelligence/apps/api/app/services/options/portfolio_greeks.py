from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.option_contract_repo import OptionContractNotFoundError, require_contract
from app.schemas.domain import Position


@dataclass(frozen=True)
class PortfolioGreeksSummary:
    dollar_delta: float
    dollar_gamma_1pct: float
    dollar_vega: float
    dollar_theta: float
    expiry_concentration: dict[str, float]
    assignment_exposure: float
    uncovered_notional: float
    margin_stress: float
    quote_observation_time: datetime | None = None
    quote_coverage_percent: float | None = None


def _fx_to_base(position: Position, base_currency: str) -> float:
    if position.currency.upper() == base_currency.upper():
        return 1.0
    from app.services.broker.ibkr_readonly import get_exchange_rate

    return float(get_exchange_rate(position.currency, base_currency))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _quote_is_fresh(observation_time: datetime | None, *, now: datetime, max_age: timedelta) -> bool:
    if observation_time is None:
        return False
    return now - _as_utc(observation_time) <= max_age


def compute_portfolio_greeks(
    positions: list[Position],
    *,
    base_currency: str = "USD",
) -> tuple[PortfolioGreeksSummary | None, list[str]]:
    exclusions: list[str] = []
    dollar_delta = 0.0
    dollar_gamma_1pct = 0.0
    dollar_vega = 0.0
    dollar_theta = 0.0
    expiry_notional: dict[str, float] = defaultdict(float)
    assignment_exposure = 0.0
    uncovered_notional = 0.0
    margin_stress = 0.0
    option_positions = [position for position in positions if position.asset_class in {"OPT", "FOP"}]
    if not option_positions:
        return None, exclusions

    now = datetime.now(timezone.utc)
    max_age = timedelta(minutes=max(settings.options_greek_max_quote_age_minutes, 1))
    fresh_contracts = 0
    oldest_quote: datetime | None = None

    stock_by_con_id = {
        position.con_id: position
        for position in positions
        if position.asset_class not in {"OPT", "FOP"} and position.con_id is not None
    }
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

        observation_time = contract.quote_timestamp or position.updated_at
        if not _quote_is_fresh(observation_time, now=now, max_age=max_age):
            exclusions.append(f"{position.symbol}:stale_or_missing_greek_quote")
            continue

        underlying = None
        if contract.underlying_con_id is not None:
            underlying = stock_by_con_id.get(contract.underlying_con_id)
        if underlying is None:
            # Contract master stores underlying ticker on `symbol` (see upsert_contract).
            underlying_symbol = (
                getattr(contract, "underlying_symbol", None) or contract.symbol or ""
            ).upper()
            if not underlying_symbol:
                exclusions.append(f"{position.symbol}:underlying_identity_missing")
                continue
            underlying = stock_by_symbol.get(underlying_symbol)
            if underlying is None:
                exclusions.append(f"{position.symbol}:underlying_symbol_unverified")
                continue
            if contract.underlying_con_id is not None:
                exclusions.append(f"{position.symbol}:underlying_con_id_fallback_symbol")

        # Count coverage only after underlying resolution succeeds.
        fresh_contracts += 1
        observation_time = _as_utc(observation_time) if observation_time is not None else None
        if observation_time is not None and (oldest_quote is None or observation_time < oldest_quote):
            oldest_quote = observation_time

        fx_rate = _fx_to_base(position, base_currency)
        qty = float(position.quantity)
        multiplier = float(position.multiplier or contract.multiplier or 100.0)
        underlying_spot = underlying.market_price if underlying else 0.0

        if contract.delta is not None:
            dollar_delta += qty * multiplier * contract.delta * underlying_spot * fx_rate
        if contract.gamma is not None and underlying_spot > 0:
            dollar_gamma_1pct += qty * multiplier * contract.gamma * (underlying_spot**2) * 0.01 * fx_rate
        if contract.vega is not None:
            dollar_vega += qty * multiplier * contract.vega * fx_rate
        if contract.theta is not None:
            dollar_theta += qty * multiplier * contract.theta * fx_rate

        notional = abs(qty * multiplier * contract.strike * fx_rate)
        expiry_notional[contract.expiration.isoformat()] += notional

        if qty < 0:
            assignment_exposure += notional
            uncovered = notional
            if contract.right.upper() == "C" and underlying is not None and underlying_spot > 0:
                shares_needed = abs(qty) * multiplier
                covered_shares = max(0.0, float(underlying.quantity))
                uncovered_shares = max(0.0, shares_needed - covered_shares)
                uncovered = uncovered_shares * underlying_spot * fx_rate
            uncovered_notional += uncovered
            # Documented stress proxy only — not IBKR margin; experimental.
            margin_stress += uncovered * 0.20
            exclusions.append(f"{position.symbol}:margin_stress_experimental")

    if fresh_contracts == 0:
        return None, exclusions

    total_expiry = sum(expiry_notional.values()) or 1.0
    expiry_concentration = {
        expiry: round(value / total_expiry * 100.0, 2)
        for expiry, value in sorted(expiry_notional.items())
    }
    quote_coverage = round(fresh_contracts / len(option_positions) * 100.0, 2)

    return (
        PortfolioGreeksSummary(
            dollar_delta=round(dollar_delta, 2),
            dollar_gamma_1pct=round(dollar_gamma_1pct, 4),
            dollar_vega=round(dollar_vega, 2),
            dollar_theta=round(dollar_theta, 2),
            expiry_concentration=expiry_concentration,
            assignment_exposure=round(assignment_exposure, 2),
            uncovered_notional=round(uncovered_notional, 2),
            margin_stress=round(margin_stress, 2),
            quote_observation_time=oldest_quote,
            quote_coverage_percent=quote_coverage,
        ),
        exclusions,
    )


def portfolio_greeks_as_dict(summary: PortfolioGreeksSummary | None) -> dict[str, Any]:
    if summary is None:
        return {}
    return {
        "portfolio_dollar_delta": summary.dollar_delta,
        "portfolio_dollar_gamma_1pct": summary.dollar_gamma_1pct,
        "portfolio_dollar_vega": summary.dollar_vega,
        "portfolio_dollar_theta": summary.dollar_theta,
        "expiry_concentration": summary.expiry_concentration,
        "assignment_exposure": summary.assignment_exposure,
        "uncovered_notional": summary.uncovered_notional,
        "margin_stress": summary.margin_stress,
        "quote_observation_time": summary.quote_observation_time.isoformat() if summary.quote_observation_time else None,
        "quote_coverage_percent": summary.quote_coverage_percent,
        "greek_units": {
            "delta": "account_currency_dollar_delta",
            "gamma": "account_currency_dollar_gamma_for_1pct_spot_move",
            "vega": "account_currency_dollar_vega",
            "theta": "account_currency_dollar_theta",
        },
        "methodology": (
            "Contract-master Greeks scaled by quantity, multiplier, and FX to account currency. "
            "Underlying resolved strictly by underlying_con_id then verified symbol (fail closed). "
            "Margin stress is a documented experimental proxy — not IBKR margin. "
            "American exercise is withheld from European Black-Scholes stress paths. "
            "Contracts with missing or stale quote/Greek timestamps are excluded."
        ),
        "methodology_status": "experimental",
    }
