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
    return get_pnl_history(account_id)


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
