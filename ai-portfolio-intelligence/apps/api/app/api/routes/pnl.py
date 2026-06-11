from __future__ import annotations

from fastapi import APIRouter, Depends
from app.api.deps import get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.pnl_tracker import get_pnl_history, record_pnl_snapshot, PortfolioPnLSnapshot

router = APIRouter(prefix="/portfolio/pnl-history", tags=["portfolio-pnl"])


from app.core.audit import log_audit_action

from typing import Optional

@router.get("", response_model=list[PortfolioPnLSnapshot])
def read_pnl_history(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    """Retrieve historical PnL records."""
    history = get_pnl_history(account_id)
    try:
        accounts = adapter.get_accounts()
        if accounts and history:
            acct_id = account_id
            if not acct_id or acct_id == "all":
                acct_id = accounts[0].id
            summary = adapter.get_account_summary(acct_id)
            current_net_liq = summary.net_liquidation
            if current_net_liq > 0:
                mock_entries = [entry for entry in history if entry.is_mock]
                if mock_entries:
                    last_mock_val = mock_entries[-1].net_liquidation
                    if last_mock_val > 0:
                        scale_factor = current_net_liq / last_mock_val
                        for entry in history:
                            if entry.is_mock:
                                entry.net_liquidation = round(entry.net_liquidation * scale_factor, 2)
                                entry.cash = round(entry.cash * scale_factor, 2)
                                entry.buying_power = round(entry.buying_power * scale_factor, 2)
                                entry.margin_requirement = round(entry.margin_requirement * scale_factor, 2)
                                entry.daily_pnl = round(entry.daily_pnl * scale_factor, 2)
                                for pos in entry.positions:
                                    pos.market_price = round(pos.market_price * scale_factor, 2)
                                    pos.market_value = round(pos.market_value * scale_factor, 2)
                                    pos.unrealized_pnl = round(pos.unrealized_pnl * scale_factor, 2)
                                    pos.daily_pnl = round(pos.daily_pnl * scale_factor, 2)
    except Exception:
        pass
    return history


@router.post("/record", response_model=PortfolioPnLSnapshot)
def create_pnl_snapshot(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    """Manually record a portfolio performance snapshot."""
    if account_id == "all":
        from app.api.routes.portfolio import _get_consolidated_summary_and_positions
        summary, positions = _get_consolidated_summary_and_positions(adapter)
        res = record_pnl_snapshot(summary, positions, "all")
        log_audit_action(
            action="pnl_snapshot_recorded",
            object_type="portfolio",
            object_id="all",
            metadata={"net_liquidation": summary.net_liquidation}
        )
        return res

    accounts = adapter.get_accounts()
    if accounts:
        acct_id = account_id or accounts[0].id
        summary = adapter.get_account_summary(acct_id)
        positions = adapter.get_positions(acct_id)
        res = record_pnl_snapshot(summary, positions, acct_id)
        log_audit_action(
            action="pnl_snapshot_recorded",
            object_type="portfolio",
            object_id=acct_id,
            metadata={"net_liquidation": summary.net_liquidation}
        )
        return res
    
    # Fallback/Dummy values if broker disconnected
    from app.schemas.domain import AccountSummary, utc_now
    dummy_summary = AccountSummary(
        account_id="DISCONNECTED",
        net_liquidation=156000.0,
        cash=32500.0,
        buying_power=125000.0,
        margin_requirement=18500.0,
        excess_liquidity=94000.0,
        total_unrealized_pnl=4200.0,
        total_realized_pnl=1200.0,
        base_currency="USD",
        data_timestamp=utc_now()
    )
    return record_pnl_snapshot(dummy_summary, [], account_id)
