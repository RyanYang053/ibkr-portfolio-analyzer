from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from app.services.options.engine import OptionContract, calculate_bs_greeks, calculate_bs_price


def fetch_ibkr_options_chain(symbol: str, current_price: float, *, max_contracts: int = 20) -> list[OptionContract]:
    """Read option marks from a connected IBKR read-only session when available."""
    from app.core.config import settings

    if settings.broker_mode != "ibkr_readonly":
        raise RuntimeError("IBKR options chain requires ibkr_readonly broker mode")

    from ib_insync import IB, Option, Stock

    from app.services.broker.ibkr_readonly import get_runtime_ibkr_config

    config = get_runtime_ibkr_config()
    ib = IB()
    host = str(config.get("host", settings.ibkr_host))
    port = int(config.get("port", settings.ibkr_port))
    client_id = int(config.get("client_id", settings.ibkr_client_id)) + 7
    ib.connect(host, port, clientId=client_id, readonly=True, timeout=8)
    try:
        underlying = Stock(symbol.upper(), "SMART", "USD")
        ib.qualifyContracts(underlying)
        params = ib.reqSecDefOptParams(underlying.symbol, "", underlying.secType, underlying.conId)
        if not params:
            raise RuntimeError(f"No IBKR option parameters for {symbol.upper()}")
        exchange = params[0].exchange
        expirations = sorted(params[0].expirations)
        if not expirations:
            raise RuntimeError(f"No IBKR expirations for {symbol.upper()}")
        expiry = expirations[0]
        strikes = sorted(float(value) for value in params[0].strikes)
        strikes = sorted(strikes, key=lambda strike: abs(strike - current_price))[: max_contracts // 2]

        contracts: list[OptionContract] = []
        expiration = date.fromisoformat(f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}")
        days = max((expiration - date.today()).days, 1)
        time_to_expiry = days / 365.0
        risk_free = 0.045

        for strike in strikes:
            for right in ("C", "P"):
                option = Option(symbol.upper(), expiration.strftime("%Y%m%d"), strike, right, exchange)
                qualified = ib.qualifyContracts(option)
                if not qualified:
                    continue
                ticker = ib.reqMktData(qualified[0], "", False, False)
                ib.sleep(1.0)
                bid = float(ticker.bid or 0.0)
                ask = float(ticker.ask or 0.0)
                if bid <= 0 or ask <= 0 or ask < bid:
                    ib.cancelMktData(qualified[0])
                    continue
                mid = (bid + ask) / 2.0
                sigma = 0.30
                if ticker.modelGreeks and ticker.modelGreeks.impliedVol:
                    sigma = float(ticker.modelGreeks.impliedVol)
                greeks = calculate_bs_greeks(current_price, strike, time_to_expiry, risk_free, sigma, right)
                contracts.append(
                    OptionContract(
                        symbol=f"{symbol.upper()}{expiration.strftime('%y%m%d')}{right}{int(strike * 1000):08d}",
                        strike=strike,
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
                        open_interest=int(ticker.openInterest or 0) or None,
                        volume=int(ticker.volume or 0) or None,
                    )
                )
                ib.cancelMktData(qualified[0])
        if not contracts:
            raise RuntimeError(f"No IBKR option quotes returned for {symbol.upper()}")
        return contracts
    finally:
        ib.disconnect()


def resolve_options_chain(symbol: str, current_price: float, *, allow_mock: bool = False) -> tuple[list[OptionContract], str]:
    from app.core.config import settings

    if settings.broker_mode == "ibkr_readonly":
        try:
            return fetch_ibkr_options_chain(symbol, current_price), "IBKR"
        except Exception:
            pass
    from app.services.options.chain_provider import fetch_live_options_chain

    chain = fetch_live_options_chain(symbol, current_price)
    return chain, "LiveYahooOptions"
