from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available
from app.services.options.engine import OptionContract


class OptionContractMaster(BaseModel):
    con_id: int
    underlying_con_id: int | None = None
    symbol: str
    local_symbol: str | None = None
    right: str
    strike: float
    expiration: date
    multiplier: float = 100.0
    currency: str = "USD"
    exchange: str | None = None
    trading_class: str | None = None
    exercise_style: str | None = None
    settlement_type: str | None = None
    last_trade_date: date | None = None
    quote_timestamp: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    rho: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    market_data_type: str | None = None
    greeks_source: str | None = None
    provider: str | None = None
    source_batch_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OptionContractNotFoundError(KeyError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM option_contracts LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _parse_quote_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _contract_to_master(contract: OptionContract, *, source_batch_id: str | None = None) -> OptionContractMaster:
    if contract.con_id is None:
        raise ValueError("Option contract con_id is required for contract master persistence")
    last_trade_date = None
    if contract.last_trade_date_or_contract_month:
        raw = str(contract.last_trade_date_or_contract_month)
        if len(raw) >= 8 and raw.isdigit():
            last_trade_date = date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
    return OptionContractMaster(
        con_id=int(contract.con_id),
        underlying_con_id=contract.underlying_con_id,
        symbol=(contract.underlying_symbol or contract.symbol).upper(),
        local_symbol=contract.local_symbol,
        right=contract.right.upper(),
        strike=float(contract.strike),
        expiration=contract.expiration,
        multiplier=float(contract.multiplier or 100.0),
        currency=(contract.currency or "USD").upper(),
        exchange=contract.exchange,
        trading_class=contract.trading_class,
        exercise_style=contract.exercise_style,
        settlement_type=contract.settlement_type,
        last_trade_date=last_trade_date,
        quote_timestamp=_parse_quote_timestamp(contract.quote_timestamp),
        bid=contract.bid,
        ask=contract.ask,
        mid=contract.mid,
        implied_volatility=contract.implied_volatility,
        delta=contract.delta,
        gamma=contract.gamma,
        vega=contract.vega,
        theta=contract.theta,
        rho=contract.rho,
        open_interest=contract.open_interest,
        volume=contract.volume,
        market_data_type=contract.market_data_type,
        greeks_source=getattr(contract, "greeks_source", None),
        provider=contract.provider,
        source_batch_id=source_batch_id,
        updated_at=_utc_now(),
    )


def _master_payload(master: OptionContractMaster) -> dict[str, Any]:
    return master.model_dump(mode="json")


def upsert_contract(contract: OptionContract, *, source_batch_id: str | None = None) -> OptionContractMaster:
    master = _contract_to_master(contract, source_batch_id=source_batch_id)
    payload = _master_payload(master)
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("option contract write", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO option_contracts (
                        con_id, underlying_con_id, symbol, local_symbol, right, strike, expiration,
                        multiplier, currency, exchange, trading_class, exercise_style, settlement_type,
                        last_trade_date, quote_timestamp, bid, ask, mid, implied_volatility,
                        delta, gamma, vega, theta, rho, open_interest, volume, market_data_type,
                        greeks_source, provider, source_batch_id, payload_json, created_at, updated_at
                    ) VALUES (
                        :con_id, :underlying_con_id, :symbol, :local_symbol, :right, :strike, :expiration,
                        :multiplier, :currency, :exchange, :trading_class, :exercise_style, :settlement_type,
                        :last_trade_date, :quote_timestamp, :bid, :ask, :mid, :implied_volatility,
                        :delta, :gamma, :vega, :theta, :rho, :open_interest, :volume, :market_data_type,
                        :greeks_source, :provider, :source_batch_id, :payload_json, :created_at, :updated_at
                    )
                    ON CONFLICT (con_id) DO UPDATE SET
                        underlying_con_id = EXCLUDED.underlying_con_id,
                        symbol = EXCLUDED.symbol,
                        local_symbol = EXCLUDED.local_symbol,
                        right = EXCLUDED.right,
                        strike = EXCLUDED.strike,
                        expiration = EXCLUDED.expiration,
                        multiplier = EXCLUDED.multiplier,
                        currency = EXCLUDED.currency,
                        exchange = EXCLUDED.exchange,
                        trading_class = EXCLUDED.trading_class,
                        exercise_style = EXCLUDED.exercise_style,
                        settlement_type = EXCLUDED.settlement_type,
                        last_trade_date = EXCLUDED.last_trade_date,
                        quote_timestamp = EXCLUDED.quote_timestamp,
                        bid = EXCLUDED.bid,
                        ask = EXCLUDED.ask,
                        mid = EXCLUDED.mid,
                        implied_volatility = EXCLUDED.implied_volatility,
                        delta = EXCLUDED.delta,
                        gamma = EXCLUDED.gamma,
                        vega = EXCLUDED.vega,
                        theta = EXCLUDED.theta,
                        rho = EXCLUDED.rho,
                        open_interest = EXCLUDED.open_interest,
                        volume = EXCLUDED.volume,
                        market_data_type = EXCLUDED.market_data_type,
                        greeks_source = EXCLUDED.greeks_source,
                        provider = EXCLUDED.provider,
                        source_batch_id = EXCLUDED.source_batch_id,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "con_id": master.con_id,
                    "underlying_con_id": master.underlying_con_id,
                    "symbol": master.symbol,
                    "local_symbol": master.local_symbol,
                    "right": master.right,
                    "strike": master.strike,
                    "expiration": master.expiration,
                    "multiplier": master.multiplier,
                    "currency": master.currency,
                    "exchange": master.exchange,
                    "trading_class": master.trading_class,
                    "exercise_style": master.exercise_style,
                    "settlement_type": master.settlement_type,
                    "last_trade_date": master.last_trade_date,
                    "quote_timestamp": master.quote_timestamp,
                    "bid": master.bid,
                    "ask": master.ask,
                    "mid": master.mid,
                    "implied_volatility": master.implied_volatility,
                    "delta": master.delta,
                    "gamma": master.gamma,
                    "vega": master.vega,
                    "theta": master.theta,
                    "rho": master.rho,
                    "open_interest": master.open_interest,
                    "volume": master.volume,
                    "market_data_type": master.market_data_type,
                    "greeks_source": master.greeks_source,
                    "provider": master.provider,
                    "source_batch_id": master.source_batch_id,
                    "payload_json": json.dumps(payload),
                    "created_at": master.updated_at,
                    "updated_at": master.updated_at,
                },
            )
            session.commit()
        return master

    get_state_store().write_json("option_contracts", str(master.con_id), payload)
    return master


def upsert_contracts(contracts: list[OptionContract], *, source_batch_id: str | None = None) -> list[OptionContractMaster]:
    masters: list[OptionContractMaster] = []
    for contract in contracts:
        if contract.con_id is None:
            continue
        masters.append(upsert_contract(contract, source_batch_id=source_batch_id))
    return masters


def get_contract(con_id: int) -> OptionContractMaster | None:
    if settings.persistence_backend == "postgres":
        require_postgres_read("option contract read", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM option_contracts WHERE con_id = :con_id"),
                {"con_id": con_id},
            ).mappings().first()
        if row is None:
            return None
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return OptionContractMaster.model_validate(payload)

    payload = get_state_store().read_json("option_contracts", str(con_id))
    if payload is None:
        return None
    return OptionContractMaster.model_validate(payload)


def require_contract(con_id: int | None) -> OptionContractMaster:
    if con_id is None:
        raise OptionContractNotFoundError("option contract con_id is required")
    contract = get_contract(int(con_id))
    if contract is None:
        raise OptionContractNotFoundError(f"option contract {con_id} not found in contract master")
    return contract
