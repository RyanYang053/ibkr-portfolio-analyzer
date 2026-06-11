from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from pydantic import BaseModel

from app.services.broker.base import BrokerAdapter
from app.schemas.domain import Position, AccountSummary

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "pnl_history.json")


class PositionPnL(BaseModel):
    symbol: str
    quantity: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    daily_pnl: float
    daily_pnl_percent: float


class PortfolioPnLSnapshot(BaseModel):
    date: str  # YYYY-MM-DD
    timestamp: str  # ISO timestamp
    net_liquidation: float
    cash: float
    buying_power: float
    margin_requirement: float
    daily_pnl: float
    daily_pnl_percent: float
    positions: list[PositionPnL]
    is_mock: bool = False



def get_pnl_history(account_id: Optional[str] = None) -> list[PortfolioPnLSnapshot]:
    """Load or initialize PnL history, optionally for a specific account or consolidated 'all'."""
    import sys
    from app.core.config import settings
    is_demo = (settings.broker_mode == "mock_ibkr_readonly") or ("pytest" in sys.modules)

    if is_demo:
        history_file = HISTORY_FILE
        if not os.path.exists(history_file):
            _initialize_mock_history(history_file)
    else:
        active_id = account_id or "default"
        history_file = os.path.join(DATA_DIR, f"pnl_history_{active_id}.json")

    try:
        if not os.path.exists(history_file):
            return []
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            history = [PortfolioPnLSnapshot(**item) for item in data]
            if not is_demo:
                history = [entry for entry in history if not entry.is_mock]
            return history
    except Exception:
        return []


def record_pnl_snapshot(summary: AccountSummary, positions: list[Position], account_id: Optional[str] = None) -> PortfolioPnLSnapshot:
    """Record a new PnL snapshot, calculating daily changes relative to the last recorded entry."""
    import sys
    from app.core.config import settings
    is_demo = (settings.broker_mode == "mock_ibkr_readonly") or ("pytest" in sys.modules)

    active_account_id = account_id or summary.account_id or "default"
    history = get_pnl_history(None if is_demo else active_account_id)
    
    today_str = date.today().isoformat()
    # Filter out existing entries for today to avoid duplicate entries for the same date
    history = [item for item in history if item.date != today_str]

    last_entry = history[-1] if history else None

    # Calculate daily PnL relative to last net_liquidation
    is_transition = False
    if last_entry and last_entry.is_mock and last_entry.net_liquidation > 0:
        deviation = abs(last_entry.net_liquidation - summary.net_liquidation) / last_entry.net_liquidation
        if deviation > 0.05:
            is_transition = True

    if last_entry and not is_transition and last_entry.net_liquidation > 0:
        daily_pnl = summary.net_liquidation - last_entry.net_liquidation
        daily_pnl_percent = (daily_pnl / last_entry.net_liquidation) * 100
    else:
        daily_pnl = 0.0
        daily_pnl_percent = 0.0

    # Build position level PnLs
    positions_pnl: list[PositionPnL] = []
    for pos in positions:
        if pos.quantity <= 0:
            continue
        
        # Try to find corresponding position from last entry to compute daily PnL
        pos_daily_pnl = 0.0
        pos_daily_pnl_pct = 0.0
        if last_entry and not is_transition:
            last_pos = next((p for p in last_entry.positions if p.symbol == pos.symbol), None)
            if last_pos and last_pos.market_price > 0:
                pos_daily_pnl = (pos.market_price - last_pos.market_price) * pos.quantity
                pos_daily_pnl_pct = ((pos.market_price - last_pos.market_price) / last_pos.market_price) * 100
        
        positions_pnl.append(
            PositionPnL(
                symbol=pos.symbol,
                quantity=pos.quantity,
                market_price=pos.market_price,
                market_value=pos.market_value,
                unrealized_pnl=pos.unrealized_pnl,
                daily_pnl=round(pos_daily_pnl, 2),
                daily_pnl_percent=round(pos_daily_pnl_pct, 2)
            )
        )

    new_snapshot = PortfolioPnLSnapshot(
        date=today_str,
        timestamp=datetime.now(timezone.utc).isoformat(),
        net_liquidation=round(summary.net_liquidation, 2),
        cash=round(summary.cash, 2),
        buying_power=round(summary.buying_power, 2),
        margin_requirement=round(summary.margin_requirement, 2),
        daily_pnl=round(daily_pnl, 2),
        daily_pnl_percent=round(daily_pnl_percent, 2),
        positions=positions_pnl,
        is_mock=is_demo
    )

    history.append(new_snapshot)
    
    # Save back to account-specific file (only if not demo/test mode)
    history_file = os.path.join(DATA_DIR, f"pnl_history_{active_account_id}.json") if (active_account_id and not is_demo) else HISTORY_FILE
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump([item.model_dump() for item in history], f, indent=2)

    return new_snapshot


def _initialize_mock_history(target_file: str = HISTORY_FILE) -> None:
    """Generate 14 days of realistic looking mock portfolio PnL history."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    start_date = date.today() - timedelta(days=14)
    history: list[PortfolioPnLSnapshot] = []
    
    # Seed values based on the MockIBKRAdapter holdings and cash
    # Total initial portfolio value ~ $156,000
    base_net_liq = 156000.0
    cash = 32500.0
    buying_power = 125000.0
    margin_req = 18500.0
    
    mock_securities = {
        "QQQ": (68, 405.0),
        "SPY": (52, 485.0),
        "MSFT": (45, 338.0),
        "META": (27, 410.0),
        "GOOGL": (70, 132.0),
        "SOXX": (38, 196.0),
        "SOFI": (650, 8.4),
        "CRM": (31, 215.0),
        "CELH": (120, 42.0),
        "NKE": (78, 82.0),
        "IONQ": (400, 11.0),
        "LAES": (900, 1.6),
        "INFQ": (750, 2.1)
    }

    # Deterministic daily performance modifiers to simulate realistic runs/dips
    daily_pnl_pcts = [-0.4, 0.8, 1.2, -0.6, -1.1, 1.5, 0.4, -0.2, 0.7, 1.1, -0.5, 1.8, 0.6, -0.3, 0.9]

    current_net_liq = base_net_liq
    for i in range(15):
        curr_date = start_date + timedelta(days=i)
        
        # Skip weekends to simulate market hours (though crypto/mock can be daily, business days look cleaner)
        if curr_date.weekday() >= 5:
            continue
            
        pct_change = daily_pnl_pcts[i % len(daily_pnl_pcts)]
        pnl_val = current_net_liq * (pct_change / 100.0)
        prev_net_liq = current_net_liq
        current_net_liq += pnl_val

        # Update position prices based on daily performance
        positions: list[PositionPnL] = []
        for symbol, (qty, avg_cost) in mock_securities.items():
            # Apply individual stock volatility
            stock_pct = pct_change + (hash(symbol + str(i)) % 5 - 2) * 0.4
            price = avg_cost * (1.0 + (stock_pct / 100.0))
            # Keep track for next iterations
            mock_securities[symbol] = (qty, price)
            
            mkt_val = qty * price
            unrealized = (price - avg_cost) * qty
            pos_pnl = mkt_val * (stock_pct / 100.0)
            
            positions.append(
                PositionPnL(
                    symbol=symbol,
                    quantity=float(qty),
                    market_price=round(price, 2),
                    market_value=round(mkt_val, 2),
                    unrealized_pnl=round(unrealized, 2),
                    daily_pnl=round(pos_pnl, 2),
                    daily_pnl_percent=round(stock_pct, 2)
                )
            )

        history.append(
            PortfolioPnLSnapshot(
                date=curr_date.isoformat(),
                timestamp=datetime.combine(curr_date, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                net_liquidation=round(current_net_liq, 2),
                cash=round(cash, 2),
                buying_power=round(buying_power, 2),
                margin_requirement=round(margin_req, 2),
                daily_pnl=round(pnl_val, 2),
                daily_pnl_percent=round(pct_change, 2),
                positions=positions,
                is_mock=True
            )
        )

    with open(target_file, "w", encoding="utf-8") as f:
        json.dump([item.model_dump() for item in history], f, indent=2)
