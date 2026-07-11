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
class OptionMarketInputsResolution:
    inputs: OptionMarketInputs | None
    status: str
    exclusions: list[str]
    methodology: str


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
    allow_demo_defaults: bool | None = None,
) -> OptionMarketInputsResolution:
    allow_defaults = (
        allow_demo_defaults
        if allow_demo_defaults is not None
        else settings.broker_mode == "mock_ibkr_readonly"
    )
    exclusions: list[str] = []
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

    if spot <= 0:
        return OptionMarketInputsResolution(
            None,
            "withheld",
            ["underlying_spot_unavailable"],
            "Option stress inputs withheld without underlying spot",
        )

    implied_volatility: float | None = None
    if underlying_symbol:
        try:
            from app.db.iv_observation_repo import read_iv_history

            history = read_iv_history(underlying_symbol)
            if history:
                implied_volatility = float(history[-1])
        except Exception:
            implied_volatility = None

    if implied_volatility is None:
        if allow_defaults:
            implied_volatility = 0.30
            exclusions.append("implied_volatility_defaulted_demo")
        else:
            return OptionMarketInputsResolution(
                None,
                "withheld",
                ["implied_volatility_unavailable"],
                "Option stress inputs withheld without implied volatility observations",
            )

    configured_rate = getattr(settings, "risk_free_rate_annual", None)
    if configured_rate is None and not allow_defaults:
        return OptionMarketInputsResolution(
            None,
            "withheld",
            ["risk_free_curve_unavailable"],
            "Option stress inputs withheld without configured risk-free curve",
        )
    risk_free_curve = float(configured_rate if configured_rate is not None else 0.045)
    if configured_rate is None:
        exclusions.append("risk_free_curve_defaulted_demo")

    dividend_curve = 0.0
    _ = underlying_con_id, expiration, currency
    return OptionMarketInputsResolution(
        OptionMarketInputs(
            spot=spot,
            implied_volatility=implied_volatility,
            risk_free_curve=risk_free_curve,
            dividend_curve=dividend_curve,
        ),
        "available",
        exclusions,
        "Observed spot with stored IV and configured risk-free curve",
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
    if implied_volatility <= 0:
        return OptionScenarioReprice(
            None,
            "withheld",
            ["implied_volatility_unavailable"],
            "European Black-Scholes repricing; implied volatility withheld",
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
