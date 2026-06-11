from __future__ import annotations

from datetime import date
from itertools import count
from threading import Lock
from typing import Any

from app.core.config import settings
from app.schemas.domain import AccountSummary, BrokerAccount, OpenOrderReadOnly, Position, Transaction
from app.services.broker.base import BrokerAdapter

import time

_runtime_config: dict[str, Any] = {}
_client_id_lock = Lock()
_client_id_offsets = count()

_cache_data: dict[str, tuple[float, Any]] = {}
_cache_lock = Lock()


def _get_from_cache(key: str, max_age: float = 5.0) -> Any | None:
    with _cache_lock:
        val = _cache_data.get(key)
        if val:
            timestamp, data = val
            if time.time() - timestamp < max_age:
                return data
        return None


def _set_in_cache(key: str, data: Any) -> None:
    with _cache_lock:
        _cache_data[key] = (time.time(), data)


def configure_runtime_ibkr(host: str, port: int, client_id: int, account_id: str | None = None) -> None:
    _runtime_config.update(
        {
            "host": host,
            "port": port,
            "client_id": client_id,
            "account_id": account_id or None,
            "read_only": True,
        }
    )
    with _cache_lock:
        _cache_data.clear()


def get_runtime_ibkr_config() -> dict[str, Any]:
    return {
        "host": _runtime_config.get("host", settings.ibkr_host),
        "port": int(_runtime_config.get("port", settings.ibkr_port)),
        "client_id": int(_runtime_config.get("client_id", settings.ibkr_client_id)),
        "account_id": _runtime_config.get("account_id", settings.ibkr_account_id),
        "read_only": True,
    }


def allocate_readonly_client_id(base_client_id: int) -> int:
    with _client_id_lock:
        return base_client_id + (next(_client_id_offsets) % 1000)


_fx_cache: dict[tuple[str, str], float] = {}


def get_exchange_rate(from_curr: str, to_curr: str) -> float:
    if not from_curr or not to_curr or from_curr == to_curr:
        return 1.0
        
    pair = (from_curr.upper(), to_curr.upper())
    if pair in _fx_cache:
        return _fx_cache[pair]
        
    import httpx
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{pair[0]}{pair[1]}=X"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        with httpx.Client() as client:
            response = client.get(url, headers=headers, timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                price = data["chart"]["result"][0]["meta"].get("regularMarketPrice")
                if price is not None and price > 0:
                    val = float(price)
                    _fx_cache[pair] = val
                    return val
    except Exception as exc:
        raise RuntimeError(f"Live FX rate unavailable for {pair[0]}/{pair[1]}") from exc

    raise RuntimeError(f"Live FX rate unavailable for {pair[0]}/{pair[1]}")


class IBKRReadOnlyAdapter(BrokerAdapter):
    """Read-only adapter for a local TWS / IB Gateway session.

    The adapter connects with `readonly=True` and exposes only the BrokerAdapter
    read methods. It never stores or accepts IBKR username/password/2FA data.
    """

    def get_accounts(self) -> list[BrokerAccount]:
        cached = _get_from_cache("accounts", max_age=30.0)
        if cached is not None:
            return cached

        with self._connect() as ib:
            account_ids = self._account_ids(ib)
            res = [
                BrokerAccount(
                    id=account_id,
                    broker_name="Interactive Brokers",
                    account_number_hash=f"ibkr:{account_id[-4:]}",
                    account_alias=f"IBKR {account_id[-4:]}",
                    account_type="IBKR",
                    base_currency="USD",
                    status="connected_readonly",
                    last_sync_at=__import__("app.schemas.domain", fromlist=["utc_now"]).utc_now(),
                )
                for account_id in account_ids
            ]
            _set_in_cache("accounts", res)
            return res

    def get_account_summary(self, account_id: str) -> AccountSummary:
        cached = _get_from_cache(f"summary:{account_id}", max_age=5.0)
        if cached is not None:
            return cached

        with self._connect() as ib:
            values = _summary_values(ib.accountSummary(account_id))
            total_unrealized = _float_value(values, "UnrealizedPnL")
            base_currency = values.get("Currency", "USD")

            res = AccountSummary(
                account_id=account_id,
                net_liquidation=_float_value(values, "NetLiquidation"),
                cash=_float_value(values, "TotalCashValue", "CashBalance", "AvailableFunds"),
                buying_power=_float_value(values, "BuyingPower"),
                margin_requirement=_float_value(values, "InitMarginReq", "FullInitMarginReq", "MaintMarginReq"),
                excess_liquidity=_float_value(values, "ExcessLiquidity"),
                total_unrealized_pnl=total_unrealized,
                total_realized_pnl=_float_value(values, "RealizedPnL"),
                base_currency=base_currency,
                data_timestamp=__import__("app.schemas.domain", fromlist=["utc_now"]).utc_now(),
            )
            _set_in_cache(f"summary:{account_id}", res)
            return res

    def get_positions(self, account_id: str) -> list[Position]:
        cached = _get_from_cache(f"positions:{account_id}", max_age=5.0)
        if cached is not None:
            return cached

        with self._connect() as ib:
            portfolio_items = ib.portfolio(account_id)
            summary_values = _summary_values(ib.accountSummary(account_id))
            base_currency = summary_values.get("Currency", "USD")
            now = __import__("app.schemas.domain", fromlist=["utc_now"]).utc_now()
            
            positions_data = []
            if not portfolio_items:
                # Fallback: read-only TWS settings often disable portfolio updates but allow positions query
                raw_positions = ib.positions()
                account_positions = [p for p in raw_positions if p.account == account_id]
                for p in account_positions:
                    contract = p.contract
                    symbol = getattr(contract, "symbol", "") or getattr(contract, "localSymbol", "")
                    sec_type = getattr(contract, "secType", "STK")
                    quantity = float(p.position or 0)
                    avg_cost = float(p.avgCost or 0)
                    market_price = 0.0
                    market_value = 0.0
                    currency = getattr(contract, "currency", "USD") or "USD"
                    
                    class PositionOnlyItem:
                        def __init__(self, contract, position, averageCost, marketPrice, marketValue, unrealizedPNL, realizedPNL):
                            self.contract = contract
                            self.position = position
                            self.averageCost = averageCost
                            self.marketPrice = marketPrice
                            self.marketValue = marketValue
                            self.unrealizedPNL = unrealizedPNL
                            self.realizedPNL = realizedPNL
                    
                    item = PositionOnlyItem(contract, quantity, avg_cost, market_price, market_value, 0.0, 0.0)
                    positions_data.append((item, symbol, sec_type, quantity, avg_cost, market_price, market_value, currency))
            else:
                for item in portfolio_items:
                    contract = item.contract
                    symbol = getattr(contract, "symbol", "") or getattr(contract, "localSymbol", "")
                    sec_type = getattr(contract, "secType", "STK")
                    quantity = float(item.position or 0)
                    avg_cost = float(item.averageCost or 0)
                    market_price = float(item.marketPrice or 0)
                    import math
                    if math.isnan(market_price):
                        market_price = 0.0
                    market_value = float(item.marketValue or 0)
                    if math.isnan(market_value):
                        market_value = 0.0
                    currency = getattr(contract, "currency", "USD") or "USD"
                    positions_data.append((item, symbol, sec_type, quantity, avg_cost, market_price, market_value, currency))

            # Calculate total value in base currency
            total_value_in_base = 0.0
            for item, symbol, sec_type, quantity, avg_cost, market_price, market_value, currency in positions_data:
                rate = get_exchange_rate(currency, base_currency)
                total_value_in_base += market_value * rate

            net_liq = _float_value(summary_values, "NetLiquidation")
            total_value = net_liq if net_liq > 0 else max(total_value_in_base, 1.0)
            
            positions: list[Position] = []
            for item, symbol, sec_type, quantity, avg_cost, market_price, market_value, currency in positions_data:
                contract = item.contract
                from app.services.broker.securities import classify_security
                sec_info = classify_security(symbol, sec_type)
                
                # Compute weight using base currency values
                rate = get_exchange_rate(currency, base_currency)
                market_value_base = market_value * rate
                weight = round(market_value_base / total_value * 100, 2)
                
                positions.append(
                    Position(
                        account_id=account_id,
                        symbol=symbol,
                        company_name=sec_info["company_name"] or getattr(contract, "localSymbol", symbol) or symbol,
                        asset_class=sec_info["asset_class"] or sec_type,
                        quantity=quantity,
                        avg_cost=avg_cost,
                        market_price=market_price,
                        market_value=market_value,
                        unrealized_pnl=float(item.unrealizedPNL or 0),
                        realized_pnl=float(item.realizedPNL or 0),
                        currency=currency,
                        exchange=getattr(contract, "exchange", "") or getattr(contract, "primaryExchange", "") or "",
                        sector=sec_info["sector"],
                        industry=sec_info["industry"],
                        portfolio_weight=weight,
                        stock_type=sec_info["stock_type"],
                        is_etf=sec_info["is_etf"],
                        is_speculative=sec_info["is_speculative"],
                        updated_at=now,
                    )
                )
            _set_in_cache(f"positions:{account_id}", positions)
            return positions

    def get_transactions(self, account_id: str, start_date: date, end_date: date) -> list[Transaction]:
        return []

    def get_open_orders_readonly(self, account_id: str) -> list[OpenOrderReadOnly]:
        with self._connect() as ib:
            orders: list[OpenOrderReadOnly] = []
            for trade in ib.openTrades():
                contract = trade.contract
                order = trade.order
                status = trade.orderStatus
                orders.append(
                    OpenOrderReadOnly(
                        account_id=account_id,
                        symbol=getattr(contract, "symbol", ""),
                        side=str(getattr(order, "action", "")),
                        quantity=float(getattr(order, "totalQuantity", 0) or 0),
                        status=str(getattr(status, "status", "")),
                    )
                )
            return orders

    def get_latest_price(self, symbol: str) -> float:
        raise NotImplementedError("IBKR latest-price lookup needs contract discovery; portfolio positions already include market price.")

    def health_check(self) -> dict[str, str]:
        config = get_runtime_ibkr_config()
        try:
            with self._connect() as ib:
                return {
                    "status": "connected" if ib.isConnected() else "not_connected",
                    "mode": "ibkr_readonly",
                    "host": str(config["host"]),
                    "port": str(config["port"]),
                    "client_id": str(config["client_id"]),
                    "account_id": str(config.get("account_id") or ""),
                    "trading": "disabled",
                }
        except Exception as exc:
            return {
                "status": "not_connected",
                "mode": "ibkr_readonly",
                "host": str(config["host"]),
                "port": str(config["port"]),
                "client_id": str(config["client_id"]),
                "account_id": str(config.get("account_id") or ""),
                "error": str(exc),
                "trading": "disabled",
            }

    def _connect(self):
        _ensure_sync_event_loop()
        try:
            from ib_insync import IB
        except ImportError as exc:
            raise NotImplementedError("ib-insync is not installed. Install API requirements first.") from exc

        config = get_runtime_ibkr_config()
        client_id = allocate_readonly_client_id(config["client_id"])
        ib = IB()
        ib.connect(
            host=config["host"],
            port=config["port"],
            clientId=client_id,
            timeout=8,
            readonly=True,
            account=config.get("account_id") or "",
        )
        # Give ib_insync background event loop time to sync positions and summaries from TWS/Gateway
        ib.sleep(1.0)
        return _IBConnection(ib)

    def _account_ids(self, ib) -> list[str]:
        configured = get_runtime_ibkr_config().get("account_id")
        if configured:
            return [configured]
        managed = ib.managedAccounts()
        if managed:
            return list(managed)
        raise NotImplementedError("Connected to IBKR, but no managed accounts were returned.")


class _IBConnection:
    def __init__(self, ib) -> None:
        self.ib = ib

    def __enter__(self):
        return self.ib

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()


def _ensure_sync_event_loop():
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed() or loop.is_running():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def _summary_values(account_values) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in account_values:
        tag = getattr(item, "tag", "")
        value = getattr(item, "value", "")
        if tag and tag not in values:
            values[tag] = value
        if getattr(item, "currency", None) and "Currency" not in values:
            values["Currency"] = item.currency
    return values


def _float_value(values: dict[str, str], *tags: str) -> float:
    for tag in tags:
        value = values.get(tag)
        if value not in (None, "", "N/A"):
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0
