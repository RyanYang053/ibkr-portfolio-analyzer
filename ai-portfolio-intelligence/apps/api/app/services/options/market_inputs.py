from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.config import settings
from app.db.option_contract_repo import OptionContractMaster
from app.services.options.engine import calculate_bs_price


@dataclass(frozen=True)
class OptionMarketInputs:
    spot: float
    implied_volatility: float
    risk_free_curve: float
    dividend_curve: float


@dataclass(frozen=True)
class OptionScenarioReprice:
    loss: float | None
    status: str
    exclusions: list[str]
    methodology: str
    repriced_mark: float | None = None


def option_market_inputs(
    *,
    underlying_con_id: int | None,
    expiration: date,
    currency: str,
    underlying_symbol: str | None = None,
) -> OptionMarketInputs:
    spot = 0.0
    if underlying_symbol:
        try:
            from app.services.market_data.http_client import request_with_retry

            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={underlying_symbol.upper()}"
            response = request_with_retry(url, timeout=4.0, max_attempts=2)
            quote = (response.json().get("quoteResponse", {}).get("result") or [None])[0]
            if quote and quote.get("regularMarketPrice"):
                spot = float(quote["regularMarketPrice"])
        except Exception:
            spot = 0.0

    implied_volatility = 0.30
    if underlying_symbol:
        try:
            from app.db.iv_observation_repo import read_iv_history

            history = read_iv_history(underlying_symbol)
            if history:
                implied_volatility = float(history[-1])
        except Exception:
            pass

    risk_free_curve = float(getattr(settings, "risk_free_rate_annual", 0.045) or 0.045)
    dividend_curve = 0.0
    _ = underlying_con_id, expiration, currency
    return OptionMarketInputs(
        spot=spot,
        implied_volatility=implied_volatility,
        risk_free_curve=risk_free_curve,
        dividend_curve=dividend_curve,
    )


def reprice_option_scenario(
    *,
    contract: OptionContractMaster,
    current_option_mark: float,
    underlying_spot: float,
    implied_volatility: float,
    risk_free_curve: float,
    dividend_curve: float,
    spot_shock_pct: float,
    volatility_shock_points: float,
    days_forward: int,
    quantity: float,
) -> OptionScenarioReprice:
    if underlying_spot <= 0:
        return OptionScenarioReprice(
            None,
            "withheld",
            ["underlying_spot_unavailable"],
            "European Black-Scholes repricing; underlying spot withheld",
        )

    days = max((contract.expiration - date.today()).days - days_forward, 1)
    shocked_spot = underlying_spot * (1.0 + spot_shock_pct / 100.0)
    shocked_vol = max(implied_volatility + volatility_shock_points, 0.01)
    repriced = calculate_bs_price(
        shocked_spot,
        contract.strike,
        days / 365.0,
        risk_free_curve,
        shocked_vol,
        contract.right,
        dividend_yield=dividend_curve,
    )
    loss = float(quantity) * contract.multiplier * (repriced - current_option_mark)
    return OptionScenarioReprice(
        loss,
        "available",
        [],
        "European Black-Scholes repricing using contract master metadata",
        repriced_mark=repriced,
    )
