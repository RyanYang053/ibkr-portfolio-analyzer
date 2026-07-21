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
    methodology_status: str = "experimental"


@dataclass(frozen=True)
class OptionScenarioReprice:
    loss: float | None
    status: str
    exclusions: list[str]
    methodology: str
    repriced_mark: float | None = None
    methodology_status: str = "experimental"


def _resolve_underlying_spot(
    *,
    underlying_con_id: int | None,
    underlying_symbol: str | None,
    positions: list | None = None,
) -> tuple[float, str | None, list[str]]:
    """Resolve underlying strictly by conId then verified symbol. Fail closed if unresolved."""
    exclusions: list[str] = []
    if positions:
        by_con = {
            p.con_id: p
            for p in positions
            if getattr(p, "con_id", None) is not None and getattr(p, "asset_class", "") not in {"OPT", "FOP"}
        }
        by_symbol = {
            str(p.symbol).upper(): p
            for p in positions
            if getattr(p, "asset_class", "") not in {"OPT", "FOP"} and float(getattr(p, "market_price", 0) or 0) > 0
        }
        if underlying_con_id is not None and underlying_con_id in by_con:
            pos = by_con[underlying_con_id]
            return float(pos.market_price), str(pos.symbol).upper(), exclusions
        if underlying_con_id is not None:
            exclusions.append("underlying_con_id_unresolved")
            return 0.0, None, exclusions
        if underlying_symbol:
            pos = by_symbol.get(underlying_symbol.upper())
            if pos is None:
                exclusions.append("underlying_symbol_unverified")
                return 0.0, None, exclusions
            return float(pos.market_price), underlying_symbol.upper(), exclusions

    if underlying_con_id is None and not underlying_symbol:
        exclusions.append("underlying_identity_missing")
        return 0.0, None, exclusions

    if underlying_con_id is not None and not underlying_symbol:
        # conId without portfolio mark or symbol verification — fail closed.
        exclusions.append("underlying_con_id_unresolved")
        return 0.0, None, exclusions

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
        exclusions.append("underlying_spot_unavailable")
    return spot, (underlying_symbol.upper() if underlying_symbol else None), exclusions


def _matched_iv(
    symbol: str,
    *,
    expiration: date,
    option_right: str | None = None,
    delta: float | None = None,
    moneyness: float | None = None,
) -> float | None:
    from app.db.iv_observation_repo import bucket_days_to_expiry, read_iv_history

    days = max((expiration - date.today()).days, 1)
    bucket = bucket_days_to_expiry(days)
    # Prefer expiry-bucketed history; optionally filter by right.
    history = read_iv_history(
        symbol,
        option_right=option_right,
        days_to_expiry=bucket,
    )
    if history:
        return float(history[-1])
    # Fallback: any history for symbol (still observed, not demo).
    history = read_iv_history(symbol)
    if history:
        return float(history[-1])
    _ = delta, moneyness
    return None


def option_market_inputs(
    *,
    underlying_con_id: int | None,
    expiration: date,
    currency: str,
    underlying_symbol: str | None = None,
    allow_demo_defaults: bool | None = None,
    positions: list | None = None,
    option_right: str | None = None,
    delta: float | None = None,
    moneyness: float | None = None,
    reporting_currency: str | None = None,
    fx_rate: float | None = None,
) -> OptionMarketInputsResolution:
    allow_defaults = (
        allow_demo_defaults
        if allow_demo_defaults is not None
        else settings.broker_mode == "mock_ibkr_readonly"
    )
    exclusions: list[str] = []

    # Dual-currency: contract currency vs account reporting FX must be present outside mock.
    if (
        reporting_currency
        and currency
        and currency.upper() != reporting_currency.upper()
        and (fx_rate is None or fx_rate <= 0)
        and not allow_defaults
    ):
        return OptionMarketInputsResolution(
            None,
            "withheld",
            ["fx_observation_required"],
            "Option stress inputs withheld without contract-to-reporting FX observation",
            methodology_status="withheld",
        )

    spot, resolved_symbol, resolve_exclusions = _resolve_underlying_spot(
        underlying_con_id=underlying_con_id,
        underlying_symbol=underlying_symbol,
        positions=positions,
    )
    exclusions.extend(resolve_exclusions)
    if spot <= 0:
        return OptionMarketInputsResolution(
            None,
            "withheld",
            exclusions or ["underlying_spot_unavailable"],
            "Option stress inputs withheld without resolved underlying",
            methodology_status="withheld",
        )

    implied_volatility: float | None = None
    if resolved_symbol:
        try:
            implied_volatility = _matched_iv(
                resolved_symbol,
                expiration=expiration,
                option_right=option_right,
                delta=delta,
                moneyness=moneyness,
            )
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
                exclusions + ["implied_volatility_unavailable"],
                "Option stress inputs withheld without expiry-/delta-matched IV observations",
                methodology_status="withheld",
            )

    configured_rate = getattr(settings, "risk_free_rate_annual", None)
    if configured_rate is None and not allow_defaults:
        return OptionMarketInputsResolution(
            None,
            "withheld",
            exclusions + ["risk_free_curve_unavailable"],
            "Option stress inputs withheld without configured risk-free curve",
            methodology_status="withheld",
        )
    risk_free_curve = float(configured_rate if configured_rate is not None else 0.045)
    if configured_rate is None:
        exclusions.append("risk_free_curve_defaulted_demo")

    # Dividend curve must be configured outside mock; do not invent yields.
    dividend_curve = float(getattr(settings, "options_dividend_yield_default", 0.0) or 0.0)
    if not hasattr(settings, "options_dividend_yield_default") and not allow_defaults:
        # Zero is an explicit flat curve when configured rate path is used; label experimental.
        exclusions.append("dividend_curve_flat_zero_experimental")

    return OptionMarketInputsResolution(
        OptionMarketInputs(
            spot=spot,
            implied_volatility=implied_volatility,
            risk_free_curve=risk_free_curve,
            dividend_curve=dividend_curve,
        ),
        "available" if not any(item.endswith("_demo") for item in exclusions) else "provisional",
        exclusions,
        (
            "Resolved underlying by conId/verified symbol; expiry-bucketed IV; "
            "configured risk-free curve. American exercise is withheld from European BS stress; "
            "IBKR portfolio-margin engines are not claimed."
        ),
        methodology_status="experimental",
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
    reporting_currency: str | None = None,
    fx_rate: float | None = None,
    exercise_style: str = "european",
) -> OptionScenarioReprice:
    exclusions: list[str] = []
    methodology_status = "experimental"

    if reporting_currency and contract.currency.upper() != reporting_currency.upper():
        if fx_rate is None or fx_rate <= 0:
            return OptionScenarioReprice(
                None,
                "withheld",
                ["fx_observation_required"],
                "Dual-currency option stress withheld without FX observation",
                methodology_status="withheld",
            )

    if underlying_spot <= 0:
        return OptionScenarioReprice(
            None,
            "withheld",
            ["underlying_spot_unavailable"],
            "European Black-Scholes repricing; underlying spot withheld",
            methodology_status="withheld",
        )
    if implied_volatility <= 0:
        return OptionScenarioReprice(
            None,
            "withheld",
            ["implied_volatility_unavailable"],
            "European Black-Scholes repricing; implied volatility withheld",
            methodology_status="withheld",
        )

    if exercise_style.lower() == "american":
        try:
            from app.services.model_governance import MethodologyNotApproved, require_methodology_status
            from app.services.options.american_pricer import try_price_american

            require_methodology_status("options_american_pricer")
        except MethodologyNotApproved:
            return OptionScenarioReprice(
                None,
                "withheld",
                ["american_exercise_not_supported", "options_american_pricer_not_approved"],
                "American exercise withheld; options_american_pricer not approved_for_personal_use",
                methodology_status="withheld",
            )
        except Exception:
            return OptionScenarioReprice(
                None,
                "withheld",
                ["american_exercise_not_supported"],
                "American exercise withheld; European Black-Scholes must not be used as a substitute",
                methodology_status="withheld",
            )

        days = max((contract.expiration - date.today()).days - days_forward, 1)
        shocked_spot = underlying_spot * (1.0 + spot_shock_pct / 100.0)
        shocked_vol = max(implied_volatility + volatility_shock_points, 0.01)
        right = "call" if str(contract.right).upper().startswith("C") else "put"
        repriced, am_exclusions = try_price_american(
            shocked_spot,
            contract.strike,
            days / 365.0,
            risk_free_curve,
            dividend_curve,
            shocked_vol,
            steps=100,
            option_type=right,
        )
        if repriced is None:
            return OptionScenarioReprice(
                None,
                "withheld",
                exclusions + am_exclusions,
                "American CRR pricer withheld on invalid inputs",
                methodology_status="withheld",
            )
        fx = float(fx_rate) if fx_rate and fx_rate > 0 else 1.0
        loss = float(quantity) * contract.multiplier * (repriced - current_option_mark) * fx
        return OptionScenarioReprice(
            loss,
            "available",
            exclusions,
            (
                "American CRR binomial repricing (options_american_pricer). "
                "IBKR portfolio-margin engines are not claimed here."
            ),
            repriced_mark=repriced,
            methodology_status="approved_for_personal_use",
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
    fx = float(fx_rate) if fx_rate and fx_rate > 0 else 1.0
    loss = float(quantity) * contract.multiplier * (repriced - current_option_mark) * fx
    return OptionScenarioReprice(
        loss,
        "available",
        exclusions,
        (
            "European Black-Scholes repricing using contract master metadata. "
            "American exercise is withheld (not substituted). "
            "IBKR portfolio-margin engines are not claimed here."
        ),
        repriced_mark=repriced,
        methodology_status=methodology_status,
    )
