from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel


class OptionContract(BaseModel):
    symbol: str
    strike: float
    right: str  # "C" | "P"
    expiration: date
    bid: float
    ask: float
    mid: float
    implied_volatility: float
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    rho: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    con_id: Optional[int] = None
    underlying_con_id: Optional[int] = None
    underlying_symbol: Optional[str] = None
    local_symbol: Optional[str] = None
    trading_class: Optional[str] = None
    last_trade_date_or_contract_month: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    multiplier: Optional[float] = None
    quote_timestamp: Optional[str] = None
    quote_age_seconds: Optional[float] = None
    market_data_type: Optional[str] = None
    provider: Optional[str] = None
    exercise_style: Optional[str] = None
    settlement_type: Optional[str] = None
    greeks_source: Optional[str] = None


def _validate_bs_inputs(S: float, K: float, T: float, sigma: float, right: str) -> None:
    if S <= 0:
        raise ValueError("Spot must be positive")
    if K <= 0:
        raise ValueError("Strike must be positive")
    if T <= 0:
        raise ValueError("Time to expiry must be positive")
    if sigma <= 0:
        raise ValueError("Volatility must be positive")
    if right.upper() not in {"C", "P"}:
        raise ValueError("Option right must be C or P")


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def calculate_bs_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    right: str,
    *,
    dividend_yield: float = 0.0,
) -> float:
    _validate_bs_inputs(S, K, T, sigma, right)
    d1 = (math.log(S / K) + (r - dividend_yield + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    discount = math.exp(-dividend_yield * T)
    if right.upper() == "C":
        price = S * discount * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm_cdf(-d2) - S * discount * norm_cdf(-d1)
    return max(0.0, round(price, 4))


def calculate_bs_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    right: str,
    *,
    dividend_yield: float = 0.0,
) -> dict[str, float]:
    _validate_bs_inputs(S, K, T, sigma, right)
    sqrt_t = math.sqrt(T)
    discount = math.exp(-dividend_yield * T)
    d1 = (math.log(S / K) + (r - dividend_yield + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    pdf_d1 = norm_pdf(d1)
    if right.upper() == "C":
        delta = discount * norm_cdf(d1)
        theta = (
            -(S * discount * pdf_d1 * sigma) / (2.0 * sqrt_t)
            + dividend_yield * S * discount * norm_cdf(d1)
            - r * K * math.exp(-r * T) * norm_cdf(d2)
        )
        rho = K * T * math.exp(-r * T) * norm_cdf(d2) / 100.0
    else:
        delta = discount * (norm_cdf(d1) - 1.0)
        theta = (
            -(S * discount * pdf_d1 * sigma) / (2.0 * sqrt_t)
            - dividend_yield * S * discount * norm_cdf(-d1)
            + r * K * math.exp(-r * T) * norm_cdf(-d2)
        )
        rho = -K * T * math.exp(-r * T) * norm_cdf(-d2) / 100.0
    gamma = discount * pdf_d1 / (S * sigma * sqrt_t)
    vega = S * discount * pdf_d1 * sqrt_t / 100.0
    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega, 4),
        "theta": round(theta / 365.0, 4),
        "rho": round(rho, 4),
    }

def generate_mock_options_chain(symbol: str, current_price: float) -> list[OptionContract]:
    if current_price <= 0:
        return []
    
    # 30 days to expiration
    expiry = date.today() + timedelta(days=30)
    T = 30.0 / 365.0
    r = 0.045  # 4.5% risk-free rate
    sigma = 0.30  # 30% volatility
    
    # Heuristic strike spacing
    if current_price > 100:
        spacing = 5.0
    elif current_price > 25:
        spacing = 2.5
    else:
        spacing = 1.0
        
    atm_strike = round(current_price / spacing) * spacing
    
    strikes = [
        atm_strike - 2 * spacing,
        atm_strike - spacing,
        atm_strike,
        atm_strike + spacing,
        atm_strike + 2 * spacing,
    ]
    
    chain = []
    quote_timestamp = datetime.now(timezone.utc).isoformat()
    for strike in strikes:
        if strike <= 0:
            continue
        # Calls
        c_price = calculate_bs_price(current_price, strike, T, r, sigma, "C")
        c_greeks = calculate_bs_greeks(current_price, strike, T, r, sigma, "C")
        chain.append(
            OptionContract(
                symbol=f"{symbol.upper()}{expiry.strftime('%y%m%d')}C{int(strike*1000):08d}",
                strike=strike,
                right="C",
                expiration=expiry,
                bid=round(c_price * 0.98, 2),
                ask=round(c_price * 1.02, 2),
                mid=c_price,
                implied_volatility=sigma,
                delta=c_greeks["delta"],
                gamma=c_greeks["gamma"],
                vega=c_greeks["vega"],
                theta=c_greeks["theta"],
                rho=c_greeks["rho"],
                open_interest=120,
                volume=45,
                multiplier=100.0,
                underlying_symbol=symbol.upper(),
                quote_timestamp=quote_timestamp,
                quote_age_seconds=0.0,
                provider="mock",
            )
        )
        # Puts
        p_price = calculate_bs_price(current_price, strike, T, r, sigma, "P")
        p_greeks = calculate_bs_greeks(current_price, strike, T, r, sigma, "P")
        chain.append(
            OptionContract(
                symbol=f"{symbol.upper()}{expiry.strftime('%y%m%d')}P{int(strike*1000):08d}",
                strike=strike,
                right="P",
                expiration=expiry,
                bid=round(p_price * 0.98, 2),
                ask=round(p_price * 1.02, 2),
                mid=p_price,
                implied_volatility=sigma,
                delta=p_greeks["delta"],
                gamma=p_greeks["gamma"],
                vega=p_greeks["vega"],
                theta=p_greeks["theta"],
                rho=p_greeks["rho"],
                open_interest=98,
                volume=32,
                multiplier=100.0,
                underlying_symbol=symbol.upper(),
                quote_timestamp=quote_timestamp,
                quote_age_seconds=0.0,
                provider="mock",
            )
        )
    return chain

def calculate_covered_call_metrics(
    stock_price: float,
    strike: float,
    premium: float,
    *,
    multiplier: float = 100.0,
) -> dict[str, Any]:
    max_profit = round(premium + max(0.0, strike - stock_price), 2)
    max_loss = round(stock_price - premium, 2)
    breakeven = round(stock_price - premium, 2)
    return {
        "max_profit": (
            f"${max_profit * multiplier:.2f} (capped at strike + premium)"
            if strike >= stock_price
            else f"${premium * multiplier:.2f} (strike is below current price)"
        ),
        "max_loss": f"${max_loss * multiplier:.2f} (if stock falls to zero)",
        "breakeven": breakeven,
    }


def calculate_cash_secured_put_metrics(
    strike: float,
    premium: float,
    *,
    multiplier: float = 100.0,
) -> dict[str, Any]:
    max_profit = round(premium, 2)
    max_loss = round(strike - premium, 2)
    breakeven = round(strike - premium, 2)
    required_cash = round(strike * multiplier, 2)
    return {
        "max_profit": f"${max_profit * multiplier:.2f} (premium received)",
        "max_loss": f"${max_loss * multiplier:.2f} (if stock falls to zero)",
        "breakeven": breakeven,
        "required_cash": required_cash,
    }

def calculate_bull_call_spread_metrics(long_strike: float, short_strike: float, net_debit: float) -> dict[str, Any]:
    width = short_strike - long_strike
    max_profit = round(width - net_debit, 2)
    max_loss = round(net_debit, 2)
    breakeven = round(long_strike + net_debit, 2)
    return {
        "max_profit": f"${max_profit * 100:.2f} (if underlying finishes above short strike)",
        "max_loss": f"${max_loss * 100:.2f} (premium debit paid)",
        "breakeven": breakeven,
    }

def calculate_bear_put_spread_metrics(long_strike: float, short_strike: float, net_debit: float) -> dict[str, Any]:
    width = long_strike - short_strike
    max_profit = round(width - net_debit, 2)
    max_loss = round(net_debit, 2)
    breakeven = round(long_strike - net_debit, 2)
    return {
        "max_profit": f"${max_profit * 100:.2f} (if underlying finishes below short strike)",
        "max_loss": f"${max_loss * 100:.2f} (premium debit paid)",
        "breakeven": breakeven,
    }

def evaluate_strategy_eligibility(
    strategy_name: str,
    strike: float,
    underlying_price: float,
    quantity_held: float,
    cash_available: float,
    account_type: str = "Margin",
    *,
    contract_multiplier: float = 100.0,
    contract_currency: str = "USD",
    account_currency: str = "USD",
    fx_rate_to_account: float | None = None,
) -> tuple[bool, str]:
    strategy_lower = strategy_name.lower()
    if fx_rate_to_account is None:
        if contract_currency.upper() == account_currency.upper():
            fx_rate_to_account = 1.0
        else:
            from app.services.broker.ibkr_readonly import get_exchange_rate

            fx_rate_to_account = get_exchange_rate(contract_currency, account_currency)

    if "covered call" in strategy_lower:
        if quantity_held < contract_multiplier:
            return False, (
                f"Ineligible for Covered Call: You own {int(quantity_held)} shares of underlying. "
                f"A standard covered call contract requires at least {int(contract_multiplier)} shares."
            )
        return True, f"Eligible (holding at least {int(contract_multiplier)} shares)."

    elif "cash-secured put" in strategy_lower:
        required_cash = strike * contract_multiplier * fx_rate_to_account
        if cash_available < required_cash:
            return False, (
                f"Ineligible for Cash-Secured Put: Requires ${required_cash:,.2f} in cash to secure "
                f"the assignment at strike ${strike:.2f} (current available cash: ${cash_available:,.2f})."
            )
        return True, f"Eligible (cash covers the ${required_cash:,.2f} securing requirement)."
        
    elif "spread" in strategy_lower:
        if account_type.lower() != "margin":
            return False, f"Review options permission: Spread strategy typically requires options multi-leg/margin approval. (current account: {account_type})."
        return True, "Eligible (requires multi-leg spread options permission)."
        
    elif "naked" in strategy_lower:
        return False, "Blocked: Naked short-option strategies are prohibited by risk policy rules."
        
    return True, "Eligible (educational candidate)."
