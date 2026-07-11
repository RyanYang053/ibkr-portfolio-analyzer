from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.option_contract_repo import upsert_contracts
from app.services.options.chain_provider import ChainResolution, OptionsChainUnavailable
from app.services.options.engine import OptionContract, calculate_bs_greeks


@dataclass(frozen=True)
class ChainDefinition:
    exchange: str
    trading_class: str
    expirations: tuple[str, ...]
    strikes: tuple[float, ...]


def select_chain_definition(
    params: list[Any],
    *,
    preferred_exchange: str = "SMART",
    preferred_trading_class: str,
) -> ChainDefinition:
    if not params:
        raise RuntimeError("No IBKR option chain definitions returned")

    ranked: list[tuple[int, Any]] = []
    for item in params:
        score = 0
        exchange = str(getattr(item, "exchange", "") or "")
        trading_class = str(getattr(item, "tradingClass", "") or "")
        if exchange.upper() == preferred_exchange.upper():
            score += 2
        if trading_class.upper() == preferred_trading_class.upper():
            score += 3
        if getattr(item, "expirations", None) and getattr(item, "strikes", None):
            score += 1
        ranked.append((score, item))

    best = max(ranked, key=lambda pair: pair[0])[1]
    expirations = tuple(sorted(str(value) for value in getattr(best, "expirations", []) or []))
    strikes = tuple(sorted(float(value) for value in getattr(best, "strikes", []) or []))
    if not expirations or not strikes:
        raise RuntimeError("Selected IBKR option chain definition is empty")
    return ChainDefinition(
        exchange=str(getattr(best, "exchange", preferred_exchange)),
        trading_class=str(getattr(best, "tradingClass", preferred_trading_class)),
        expirations=expirations,
        strikes=strikes,
    )


def select_expirations(
    expirations: tuple[str, ...] | list[str],
    *,
    min_dte: int,
    max_dte: int,
    max_expirations: int,
) -> list[str]:
    today = date.today()
    eligible: list[tuple[int, str]] = []
    for raw in expirations:
        expiry = date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
        dte = (expiry - today).days
        if min_dte <= dte <= max_dte:
            eligible.append((dte, raw))
    eligible.sort(key=lambda item: item[0])
    return [item[1] for item in eligible[:max_expirations]]


def _expiration_date(raw: str) -> date:
    return date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")


def _greeks_from_ticker(
    ticker: Any,
    *,
    current_price: float,
    strike: float,
    time_to_expiry: float,
    right: str,
    risk_free: float,
) -> tuple[dict[str, float], float, str]:
    if ticker.modelGreeks and ticker.modelGreeks.impliedVol:
        sigma = float(ticker.modelGreeks.impliedVol)
        greeks = {
            "delta": float(ticker.modelGreeks.delta or 0.0),
            "gamma": float(ticker.modelGreeks.gamma or 0.0),
            "vega": float(ticker.modelGreeks.vega or 0.0),
            "theta": float(ticker.modelGreeks.theta or 0.0),
            "rho": float(getattr(ticker.modelGreeks, "rho", 0.0) or 0.0),
        }
        return greeks, sigma, "broker_model"
    sigma = 0.30
    greeks = calculate_bs_greeks(current_price, strike, time_to_expiry, risk_free, sigma, right)
    return greeks, sigma, "internal_bs_fallback"


def fetch_ibkr_options_chain(symbol: str, current_price: float, *, max_contracts: int | None = None) -> list[OptionContract]:
    """Read option marks from a connected IBKR read-only session when available."""
    if settings.broker_mode != "ibkr_readonly":
        raise RuntimeError("IBKR options chain requires ibkr_readonly broker mode")

    from ib_insync import IB, Option, Stock

    from app.services.broker.ibkr_readonly import get_runtime_ibkr_config

    max_contracts = max_contracts or settings.options_max_contracts
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

        chain_def = select_chain_definition(
            params,
            preferred_exchange="SMART",
            preferred_trading_class=symbol.upper(),
        )
        expirations = select_expirations(
            chain_def.expirations,
            min_dte=settings.options_min_dte,
            max_dte=settings.options_max_dte,
            max_expirations=settings.options_max_expirations,
        )
        if not expirations:
            raise RuntimeError(f"No IBKR expirations in DTE window for {symbol.upper()}")

        strikes = sorted(chain_def.strikes, key=lambda strike: abs(strike - current_price))
        per_expiry = max(max_contracts // max(len(expirations), 1), 4)
        selected_strikes = strikes[: per_expiry // 2]

        option_requests: list[tuple[Option, date, float, str]] = []
        for expiry in expirations:
            expiration = _expiration_date(expiry)
            for strike in selected_strikes:
                for right in ("C", "P"):
                    option_requests.append(
                        (
                            Option(
                                symbol.upper(),
                                expiration.strftime("%Y%m%d"),
                                strike,
                                right,
                                chain_def.exchange,
                            ),
                            expiration,
                            strike,
                            right,
                        )
                    )

        qualified_pairs: list[tuple[Any, date, float, str]] = []
        for option, expiration, strike, right in option_requests:
            qualified = ib.qualifyContracts(option)
            if qualified:
                qualified_pairs.append((qualified[0], expiration, strike, right))

        tickers: list[tuple[Any, Any, date, float, str]] = []
        for contract, expiration, strike, right in qualified_pairs[:max_contracts]:
            ticker = ib.reqMktData(contract, "", False, False)
            tickers.append((contract, ticker, expiration, strike, right))

        deadline = time.monotonic() + settings.options_quote_timeout_seconds
        while time.monotonic() < deadline:
            if all(
                (float(ticker.bid or 0.0) > 0 and float(ticker.ask or 0.0) > 0)
                or (ticker.modelGreeks and ticker.modelGreeks.impliedVol)
                for _, ticker, _, _, _ in tickers
            ):
                break
            ib.sleep(0.2)

        contracts: list[OptionContract] = []
        risk_free = float(getattr(settings, "risk_free_rate_annual", 0.045) or 0.045)
        source_batch_id = str(uuid.uuid4())

        for contract, ticker, expiration, strike, right in tickers:
            bid = float(ticker.bid or 0.0)
            ask = float(ticker.ask or 0.0)
            if bid <= 0 or ask <= 0 or ask < bid:
                ib.cancelMktData(contract)
                continue
            mid = (bid + ask) / 2.0
            days = max((expiration - date.today()).days, 1)
            time_to_expiry = days / 365.0
            greeks, sigma, greeks_source = _greeks_from_ticker(
                ticker,
                current_price=current_price,
                strike=strike,
                time_to_expiry=time_to_expiry,
                right=right,
                risk_free=risk_free,
            )
            quote_time = getattr(ticker, "time", None)
            quote_timestamp = quote_time.isoformat() if hasattr(quote_time, "isoformat") else None
            quote_age_seconds = None
            if quote_time is not None and hasattr(quote_time, "timestamp"):
                quote_age_seconds = max(
                    0.0,
                    datetime.now(timezone.utc).timestamp() - quote_time.timestamp(),
                )
            contracts.append(
                OptionContract(
                    symbol=getattr(contract, "localSymbol", None)
                    or f"{symbol.upper()}{expiration.strftime('%y%m%d')}{right}{int(strike * 1000):08d}",
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
                    con_id=getattr(contract, "conId", None),
                    underlying_con_id=underlying.conId,
                    underlying_symbol=symbol.upper(),
                    local_symbol=getattr(contract, "localSymbol", None),
                    trading_class=getattr(contract, "tradingClass", None),
                    last_trade_date_or_contract_month=getattr(contract, "lastTradeDateOrContractMonth", None),
                    exchange=getattr(contract, "exchange", chain_def.exchange),
                    currency=getattr(contract, "currency", "USD"),
                    multiplier=float(getattr(contract, "multiplier", 100) or 100),
                    quote_timestamp=quote_timestamp,
                    quote_age_seconds=quote_age_seconds,
                    market_data_type=str(getattr(ticker, "marketDataType", "")) or None,
                    provider="IBKR",
                    exercise_style=None,
                    settlement_type=None,
                    greeks_source=greeks_source,
                )
            )
            ib.cancelMktData(contract)

        if not contracts:
            raise RuntimeError(f"No IBKR option quotes returned for {symbol.upper()}")

        upsert_contracts(contracts, source_batch_id=source_batch_id)
        return contracts
    finally:
        ib.disconnect()


def resolve_options_chain(symbol: str, current_price: float, *, allow_mock: bool = False) -> ChainResolution:
    errors: list[dict[str, str]] = []
    attempts: list[dict[str, str]] = []

    if settings.broker_mode == "ibkr_readonly":
        try:
            contracts = fetch_ibkr_options_chain(symbol, current_price)
            attempts.append({"provider": "IBKR", "status": "success"})
            return ChainResolution(
                contracts=contracts,
                selected_provider="IBKR",
                provider_attempts=attempts,
            )
        except Exception as exc:
            errors.append({"provider": "IBKR", "error": str(exc)})
            attempts.append({"provider": "IBKR", "status": "failed", "error": str(exc)})

    from app.services.options.chain_provider import fetch_live_options_chain

    try:
        contracts = fetch_live_options_chain(
            symbol,
            current_price,
            max_expirations=settings.options_max_expirations,
        )
        attempts.append({"provider": "LiveYahooOptions", "status": "success"})
        return ChainResolution(
            contracts=contracts,
            selected_provider="LiveYahooOptions",
            provider_attempts=attempts,
        )
    except Exception as exc:
        errors.append({"provider": "LiveYahooOptions", "error": str(exc)})
        attempts.append({"provider": "LiveYahooOptions", "status": "failed", "error": str(exc)})

    raise OptionsChainUnavailable(errors)
