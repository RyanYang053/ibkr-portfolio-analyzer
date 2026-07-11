from __future__ import annotations

from typing import Any


def quantlib_available() -> bool:
    try:
        import QuantLib as ql  # noqa: F401

        return True
    except ImportError:
        return False


def benchmark_option_price(
    *,
    spot: float,
    strike: float,
    days_to_expiry: int,
    risk_free_rate: float,
    volatility: float,
    right: str = "C",
    dividend_yield: float = 0.0,
) -> dict[str, Any] | None:
    """Independent QuantLib Black-Scholes benchmark for internal validation."""
    if not quantlib_available():
        return None
    import QuantLib as ql

    today = ql.Date.todaysDate()
    expiry = today + int(days_to_expiry)
    spot_handle = ql.QuoteHandle(ql.SimpleQuote(spot))
    risk_free_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, risk_free_rate, ql.Actual365Fixed()))
    dividend_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, dividend_yield, ql.Actual365Fixed()))
    flat_vol = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), volatility, ql.Actual365Fixed()))
    process = ql.BlackScholesMertonProcess(spot_handle, dividend_ts, risk_free_ts, flat_vol)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if right.upper() == "C" else ql.Option.Put, strike)
    exercise = ql.EuropeanExercise(expiry)
    option = ql.VanillaOption(payoff, exercise)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    price = float(option.NPV())
    delta = float(option.delta())
    gamma = float(option.gamma())
    vega = float(option.vega()) / 100.0
    theta = float(option.theta()) / 365.0
    rho = float(option.rho()) / 100.0
    return {
        "price": round(price, 4),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega, 4),
        "theta": round(theta, 4),
        "rho": round(rho, 4),
        "engine": "QuantLib.AnalyticEuropeanEngine",
    }


def compare_with_internal_bs(
    *,
    spot: float,
    strike: float,
    days_to_expiry: int,
    risk_free_rate: float,
    volatility: float,
    right: str = "C",
    tolerance: float = 0.05,
    dividend_yield: float = 0.0,
) -> dict[str, Any]:
    from app.services.options.engine import calculate_bs_greeks, calculate_bs_price

    internal_price = calculate_bs_price(
        spot, strike, days_to_expiry / 365.0, risk_free_rate, volatility, right, dividend_yield=dividend_yield
    )
    internal_greeks = calculate_bs_greeks(
        spot, strike, days_to_expiry / 365.0, risk_free_rate, volatility, right, dividend_yield=dividend_yield
    )
    benchmark = benchmark_option_price(
        spot=spot,
        strike=strike,
        days_to_expiry=days_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
        right=right,
        dividend_yield=dividend_yield,
    )
    if benchmark is None:
        return {
            "status": "quantlib_unavailable",
            "internal_price": internal_price,
            "internal_greeks": internal_greeks,
        }
    price_gap = abs(benchmark["price"] - internal_price)
    return {
        "status": "within_tolerance" if price_gap <= tolerance else "diverged",
        "price_gap": round(price_gap, 4),
        "internal_price": internal_price,
        "benchmark_price": benchmark["price"],
        "internal_greeks": internal_greeks,
        "benchmark_greeks": benchmark,
    }
