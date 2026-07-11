from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.options.engine import OptionContract


@dataclass(frozen=True)
class OptionLiquidityPolicy:
    max_quote_age_seconds: int = 120
    max_bid_ask_spread_percent: float = 15.0
    min_open_interest: int = 50
    min_volume: int = 1
    require_open_interest: bool = True
    require_volume: bool = True
    min_bid: float = 0.05


def spread_percent(contract: OptionContract) -> float | None:
    if contract.bid <= 0 or contract.ask <= 0 or contract.ask < contract.bid:
        return None
    mid = contract.mid if contract.mid > 0 else (contract.bid + contract.ask) / 2.0
    if mid <= 0:
        return None
    return (contract.ask - contract.bid) / mid * 100.0


def is_quote_fresh(contract: OptionContract, now: datetime, *, max_age_seconds: int) -> bool:
    if contract.quote_age_seconds is not None:
        return contract.quote_age_seconds <= max_age_seconds
    if not contract.quote_timestamp:
        return False
    try:
        quote_time = datetime.fromisoformat(contract.quote_timestamp.replace("Z", "+00:00"))
        if quote_time.tzinfo is None:
            quote_time = quote_time.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age = (now.astimezone(timezone.utc) - quote_time.astimezone(timezone.utc)).total_seconds()
    return age <= max_age_seconds


def is_liquid(contract: OptionContract, policy: OptionLiquidityPolicy, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if contract.bid < policy.min_bid:
        return False
    if not is_quote_fresh(contract, now, max_age_seconds=policy.max_quote_age_seconds):
        return False
    spread = spread_percent(contract)
    if spread is None or spread > policy.max_bid_ask_spread_percent:
        return False
    if policy.require_open_interest:
        if contract.open_interest is None or contract.open_interest < policy.min_open_interest:
            return False
    elif contract.open_interest is not None and contract.open_interest < policy.min_open_interest:
        return False

    if policy.require_volume:
        if contract.volume is None or contract.volume < policy.min_volume:
            return False
    elif contract.volume is not None and contract.volume < policy.min_volume:
        return False
    return True


def is_otm_call(contract: OptionContract, spot: float) -> bool:
    return contract.right.upper() == "C" and contract.strike >= spot


def is_otm_put(contract: OptionContract, spot: float) -> bool:
    return contract.right.upper() == "P" and contract.strike <= spot
