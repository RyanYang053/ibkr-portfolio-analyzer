from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.domain import AccountSummary, Position

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "pnl_history.json")
_FILE_LOCK = Lock()


class PositionPnL(BaseModel):
    symbol: str
    con_id: int | None = None
    currency: str = "USD"
    contract_multiplier: float = 1.0
    quantity: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    daily_pnl: float
    daily_pnl_percent: float
    quantity_changed: bool = False


class PortfolioPnLSnapshot(BaseModel):
    date: str
    timestamp: str
    net_liquidation: float
    cash: float
    buying_power: float
    margin_requirement: float
    # Compatibility fields: these are account-value changes, not cash-flow-adjusted
    # investment performance.
    daily_pnl: float
    daily_pnl_percent: float
    positions: list[PositionPnL]
    is_mock: bool = False
    external_cash_flow: float | None = None
    investment_return_percent: float | None = None
    data_quality: dict[str, str] = Field(default_factory=dict)


def _history_path(account_id: Optional[str], is_demo: bool) -> str:
    if is_demo:
        return HISTORY_FILE
    return os.path.join(DATA_DIR, f"pnl_history_{account_id or 'default'}.json")


def _is_demo_mode() -> bool:
    import sys

    from app.core.config import settings

    return settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules


def _atomic_write(path: str, payload: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _FILE_LOCK:
        fd, temporary_path = tempfile.mkstemp(prefix="pnl_history_", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def get_pnl_history(account_id: Optional[str] = None) -> list[PortfolioPnLSnapshot]:
    """Load PnL/account-value history for one account or demo mode.

    Corrupted history is surfaced as an error rather than silently converted into an
    empty time series, because silent loss of history can invalidate risk metrics.
    """

    is_demo = _is_demo_mode()
    store_key = "demo" if is_demo else (account_id or "default")
    history_file = _history_path(account_id, is_demo)
    if is_demo and not os.path.exists(history_file):
        _initialize_mock_history(history_file)

    from app.db.legacy_bridge import read_json_with_legacy

    raw = read_json_with_legacy("pnl_history", store_key, history_file if os.path.exists(history_file) else None, default=[])
    if not raw:
        return []

    try:
        if not isinstance(raw, list):
            raise RuntimeError(f"PnL history must contain a JSON array: {store_key}")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"PnL history is unreadable: {store_key}") from exc

    history = [PortfolioPnLSnapshot(**item) for item in raw]
    if not is_demo:
        history = [entry for entry in history if not entry.is_mock]
    return sorted(history, key=lambda item: (item.date, item.timestamp))


def record_pnl_snapshot(
    summary: AccountSummary,
    positions: list[Position],
    account_id: Optional[str] = None,
) -> PortfolioPnLSnapshot:
    """Record an end-of-day account-value snapshot.

    `daily_pnl` is retained for API compatibility but is explicitly an account-value
    change. A true investment return is withheld until deposits, withdrawals,
    transfers, dividends, fees, and trade cash flows are imported.
    """

    is_demo = _is_demo_mode()
    active_account_id = account_id or summary.account_id or "default"
    history = get_pnl_history(None if is_demo else active_account_id)

    today = date.today().isoformat()
    history = [item for item in history if item.date != today]
    last_entry = history[-1] if history else None

    external_cash_flow = None
    investment_return_percent = None
    investment_return_status = "withheld_missing_coverage"
    try:
        from app.services.market_data.fx_store import make_transaction_fx_resolver
        from app.services.portfolio.ledger_coverage import (
            external_cash_flows_for_interval,
            ledger_covers_period,
            load_ledger_coverage,
        )
        from app.services.portfolio.transaction_store import get_transactions

        transactions = get_transactions(active_account_id)
        coverage = load_ledger_coverage(active_account_id)
        fx_resolver = make_transaction_fx_resolver()
        if last_entry and coverage:
            interval_start = date.fromisoformat(last_entry.date)
            interval_end = date.fromisoformat(today)
            if ledger_covers_period(coverage, interval_start, interval_end):
                external_cash_flow = round(
                    external_cash_flows_for_interval(
                        transactions,
                        interval_start,
                        interval_end,
                        summary.base_currency,
                        fx_resolver,
                    ),
                    2,
                )
                if last_entry.net_liquidation != 0:
                    investment_return_percent = round(
                        (summary.net_liquidation - external_cash_flow) / last_entry.net_liquidation - 1.0,
                        6,
                    ) * 100.0
                investment_return_status = "cash_flow_adjusted"
    except Exception as exc:
        external_cash_flow = None
        investment_return_percent = None
        investment_return_status = f"withheld_error:{type(exc).__name__}"

    is_transition = False
    if last_entry and last_entry.is_mock and last_entry.net_liquidation > 0:
        deviation = abs(last_entry.net_liquidation - summary.net_liquidation) / last_entry.net_liquidation
        is_transition = deviation > 0.05

    if last_entry and not is_transition and last_entry.net_liquidation != 0:
        account_value_change = summary.net_liquidation - last_entry.net_liquidation
        account_value_change_percent = account_value_change / abs(last_entry.net_liquidation) * 100.0
    else:
        account_value_change = 0.0
        account_value_change_percent = 0.0

    positions_pnl: list[PositionPnL] = []
    for position in positions:
        if position.quantity == 0:
            continue

        position_change = 0.0
        position_change_percent = 0.0
        quantity_changed = False
        if last_entry and not is_transition:
            previous = next(
                (
                    item
                    for item in last_entry.positions
                    if item.symbol == position.symbol and item.con_id == position.con_id
                ),
                None,
            )
            if previous and previous.market_price > 0:
                quantity_changed = abs(previous.quantity - position.quantity) > 1e-9
                if position.asset_class in {"OPT", "FOP"} or position.currency != summary.base_currency:
                    position_change = 0.0
                    position_change_percent = 0.0
                else:
                    position_change = previous.quantity * (position.market_price - previous.market_price)
                    position_change_percent = (
                        (position.market_price / previous.market_price - 1.0) * 100.0
                    )

        positions_pnl.append(
            PositionPnL(
                symbol=position.symbol,
                con_id=position.con_id,
                currency=position.currency,
                contract_multiplier=float(position.multiplier or 1.0),
                quantity=position.quantity,
                market_price=position.market_price,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
                daily_pnl=round(position_change, 2),
                daily_pnl_percent=round(position_change_percent, 4),
                quantity_changed=quantity_changed,
            )
        )

    snapshot = PortfolioPnLSnapshot(
        date=today,
        timestamp=datetime.now(timezone.utc).isoformat(),
        net_liquidation=round(summary.net_liquidation, 2),
        cash=round(summary.cash, 2),
        buying_power=round(summary.buying_power, 2),
        margin_requirement=round(summary.margin_requirement, 2),
        daily_pnl=round(account_value_change, 2),
        daily_pnl_percent=round(account_value_change_percent, 4),
        positions=positions_pnl,
        is_mock=is_demo,
        external_cash_flow=external_cash_flow,
        investment_return_percent=investment_return_percent,
        data_quality={
            "daily_pnl": "account_value_change_not_cash_flow_adjusted",
            "investment_return": investment_return_status,
            "position_pnl": "price_effect_estimate; quantity changes flagged",
        },
    )

    history.append(snapshot)
    store_key = "demo" if is_demo else active_account_id
    from app.db.legacy_bridge import write_json_state

    write_json_state("pnl_history", store_key, [item.model_dump() for item in history])
    history_file = _history_path(None if is_demo else active_account_id, is_demo)
    _atomic_write(history_file, [item.model_dump() for item in history])
    return snapshot


def _stable_offset(symbol: str, index: int) -> int:
    digest = hashlib.sha256(f"{symbol}:{index}".encode("utf-8")).digest()
    return digest[0] % 5 - 2


def _initialize_mock_history(target_file: str = HISTORY_FILE) -> None:
    """Generate reproducible demo history, clearly labeled as mock."""

    start_date = date.today() - timedelta(days=14)
    history: list[PortfolioPnLSnapshot] = []
    base_net_liquidation = 156_000.0
    cash = 32_500.0
    buying_power = 125_000.0
    margin_requirement = 18_500.0

    original_lots = {
        "QQQ": (68.0, 405.0),
        "SPY": (52.0, 485.0),
        "MSFT": (45.0, 338.0),
        "META": (27.0, 410.0),
        "GOOGL": (70.0, 132.0),
        "SOXX": (38.0, 196.0),
        "SOFI": (650.0, 8.4),
        "CRM": (31.0, 215.0),
        "CELH": (120.0, 42.0),
        "NKE": (78.0, 82.0),
        "IONQ": (400.0, 11.0),
        "LAES": (900.0, 1.6),
        "INFQ": (750.0, 2.1),
    }
    current_prices = {symbol: cost for symbol, (_, cost) in original_lots.items()}
    daily_changes = [-0.4, 0.8, 1.2, -0.6, -1.1, 1.5, 0.4, -0.2, 0.7, 1.1, -0.5, 1.8, 0.6, -0.3, 0.9]

    current_net_liquidation = base_net_liquidation
    for index in range(15):
        current_date = start_date + timedelta(days=index)
        if current_date.weekday() >= 5:
            continue

        portfolio_change_percent = daily_changes[index % len(daily_changes)]
        account_value_change = current_net_liquidation * portfolio_change_percent / 100.0
        current_net_liquidation += account_value_change
        position_rows: list[PositionPnL] = []

        for symbol, (quantity, original_cost) in original_lots.items():
            security_change_percent = portfolio_change_percent + _stable_offset(symbol, index) * 0.4
            previous_price = current_prices[symbol]
            current_price = previous_price * (1.0 + security_change_percent / 100.0)
            current_prices[symbol] = current_price
            market_value = quantity * current_price
            position_rows.append(
                PositionPnL(
                    symbol=symbol,
                    quantity=quantity,
                    market_price=round(current_price, 4),
                    market_value=round(market_value, 2),
                    unrealized_pnl=round((current_price - original_cost) * quantity, 2),
                    daily_pnl=round((current_price - previous_price) * quantity, 2),
                    daily_pnl_percent=round(security_change_percent, 4),
                )
            )

        history.append(
            PortfolioPnLSnapshot(
                date=current_date.isoformat(),
                timestamp=datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                net_liquidation=round(current_net_liquidation, 2),
                cash=cash,
                buying_power=buying_power,
                margin_requirement=margin_requirement,
                daily_pnl=round(account_value_change, 2),
                daily_pnl_percent=round(portfolio_change_percent, 4),
                positions=position_rows,
                is_mock=True,
                data_quality={
                    "daily_pnl": "mock_account_value_change",
                    "investment_return": "mock_demo_only",
                },
            )
        )

    _atomic_write(target_file, [item.model_dump() for item in history])
