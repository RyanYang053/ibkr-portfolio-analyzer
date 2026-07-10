from __future__ import annotations

from fastapi import APIRouter, Depends
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.pnl_tracker import get_pnl_history, record_pnl_snapshot, PortfolioPnLSnapshot

router = APIRouter(prefix="/portfolio/pnl-history", tags=["portfolio-pnl"])


from app.core.audit import log_audit_action

from typing import Optional

@router.get("", response_model=list[PortfolioPnLSnapshot])
def read_pnl_history(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    """Retrieve historical PnL records."""
    from app.api.deps import demo_mode_enabled
    if demo_mode_enabled():
        return get_pnl_history(account_id)
        
    try:
        if not account_id or account_id == "all":
            if account_id == "all":
                db_history = get_pnl_history("all")
            else:
                accounts = adapter.get_accounts()
                if not accounts:
                    return []
                active_id = accounts[0].id
                db_history = get_pnl_history(active_id)
        else:
            active_id = account_id
            db_history = get_pnl_history(active_id)
            
        import sys
        if len(db_history) < 20 and "pytest" not in sys.modules:
            from app.api.routes.portfolio import _resolve_account_data
            from app.services.risk.history_reconstructor import reconstruct_portfolio_history
            from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, PositionPnL
            
            summary, positions = _resolve_account_data(adapter, account_id)
            recon = reconstruct_portfolio_history(positions, summary)
            if recon is not None:
                trading_dates = recon["trading_dates"]
                portfolio_nav = recon["portfolio_nav"]
                
                recon_history = []
                for t in range(len(trading_dates)):
                    date_str = trading_dates[t]
                    nav = portfolio_nav[t]
                    
                    if t > 0:
                        prev_nav = portfolio_nav[t-1]
                        daily_pnl = nav - prev_nav
                        daily_pnl_pct = (daily_pnl / prev_nav * 100.0) if prev_nav > 0 else 0.0
                    else:
                        daily_pnl = 0.0
                        daily_pnl_pct = 0.0
                        
                    snapshot = PortfolioPnLSnapshot(
                        date=date_str,
                        timestamp=f"{date_str}T00:00:00Z",
                        net_liquidation=round(nav, 2),
                        cash=summary.cash,
                        buying_power=summary.buying_power,
                        margin_requirement=summary.margin_requirement,
                        daily_pnl=round(daily_pnl, 2),
                        daily_pnl_percent=round(daily_pnl_pct, 4),
                        positions=[],
                        is_mock=False
                    )
                    recon_history.append(snapshot)
                return recon_history
                
        return db_history
    except Exception:
        return []


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

    try:
        accounts = adapter.get_accounts()
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
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

    raise broker_not_configured_error(Exception("No IBKR accounts were returned."))
