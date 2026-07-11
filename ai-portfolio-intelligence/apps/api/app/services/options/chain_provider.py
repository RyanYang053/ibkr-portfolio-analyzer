from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.services.market_data.http_client import request_with_retry
from app.services.options.engine import OptionContract, calculate_bs_greeks


@dataclass(frozen=True)
class ChainResolution:
    contracts: list[OptionContract]
    selected_provider: str
    provider_attempts: list[dict[str, str]]


class OptionsChainUnavailable(RuntimeError):
    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        attempted = ", ".join(item.get("provider", "unknown") for item in errors)
        super().__init__(f"Live options chain unavailable after attempting: {attempted}")


def _parse_expiration(value: Any) -> date:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value)).date()
    return date.fromisoformat(str(value)[:10])


def fetch_live_options_chain(symbol: str, current_price: float, *, max_expirations: int = 1) -> list[OptionContract]:
    if current_price <= 0:
        raise RuntimeError(f"Cannot fetch options chain without a positive underlying price for {symbol.upper()}")

    url = f"https://query2.finance.yahoo.com/v7/finance/options/{symbol.upper()}"
    response = request_with_retry(url, timeout=6.0, max_attempts=3)
    payload = response.json()
    result = (payload.get("optionChain", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Live options chain unavailable for {symbol.upper()}")

    expirations = [int(value) for value in result.get("expirationDates") or []]
    if not expirations:
        raise RuntimeError(f"No option expirations for {symbol.upper()}")

    chain: list[OptionContract] = []
    r = 0.045
    for expiration_ts in expirations[:max_expirations]:
        detail_url = f"{url}?date={expiration_ts}"
        detail_response = request_with_retry(detail_url, timeout=6.0, max_attempts=3)
        detail = (detail_response.json().get("optionChain", {}).get("result") or [None])[0]
        if not detail:
            continue
        options = detail.get("options") or []
        if not options:
            continue
        option_block = options[0]
        expiration = _parse_expiration(option_block.get("expirationDate") or expiration_ts)
        days = max((expiration - date.today()).days, 1)
        time_to_expiry = days / 365.0

        for right, rows in (("C", option_block.get("calls") or []), ("P", option_block.get("puts") or [])):
            for row in rows:
                strike = float(row.get("strike") or 0.0)
                if strike <= 0:
                    continue
                bid = float(row.get("bid") or 0.0)
                ask = float(row.get("ask") or 0.0)
                if bid <= 0 or ask <= 0 or ask < bid:
                    continue
                mid = (bid + ask) / 2.0
                implied = row.get("impliedVolatility")
                if implied in (None, 0):
                    continue
                sigma = float(implied)
                if not math.isfinite(sigma) or sigma <= 0:
                    continue
                greeks = calculate_bs_greeks(current_price, strike, time_to_expiry, r, sigma, right)
                chain.append(
                    OptionContract(
                        symbol=str(
                            row.get("contractSymbol")
                            or f"{symbol.upper()}{expiration.strftime('%y%m%d')}{right}{int(strike * 1000):08d}"
                        ),
                        strike=round(strike, 2),
                        right=right,
                        expiration=expiration,
                        bid=round(bid, 2),
                        ask=round(ask, 2),
                        mid=round(mid, 2),
                        implied_volatility=round(sigma, 4),
                        delta=greeks["delta"],
                        gamma=greeks["gamma"],
                        vega=greeks["vega"],
                        theta=greeks["theta"],
                        rho=greeks["rho"],
                        open_interest=int(row.get("openInterest") or 0) or None,
                        volume=int(row.get("volume") or 0) or None,
                        underlying_symbol=symbol.upper(),
                        multiplier=100.0,
                        quote_timestamp=datetime.now(timezone.utc).isoformat(),
                        quote_age_seconds=0.0,
                        provider="LiveYahooOptions",
                        greeks_source="internal_bs",
                    )
                )

    if not chain:
        raise RuntimeError(f"Live options chain empty for {symbol.upper()}")

    chain.sort(key=lambda item: (abs(item.strike - current_price), item.expiration, item.right))
    return chain[:20]


def atm_implied_volatility(chain: list[OptionContract], current_price: float) -> float | None:
    if not chain or current_price <= 0:
        return None
    atm = min(chain, key=lambda item: abs(item.strike - current_price))
    if atm.implied_volatility and math.isfinite(atm.implied_volatility):
        return float(atm.implied_volatility)
    return None
