from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.account_deps import resolve_authorized_account_id, resolve_authorized_account_ids
from app.api.auth_deps import Principal, get_current_principal, require_scope
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.core.audit import log_audit_action
from app.services.broker.base import BrokerAdapter
from app.services.data_quality.validation import validate_and_gate_snapshot
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, get_pnl_history, record_pnl_snapshot

router = APIRouter(
    prefix="/portfolio/pnl-history",
    tags=["portfolio-pnl"],
    dependencies=[Depends(get_current_principal)],
)


@router.get("", response_model=list[PortfolioPnLSnapshot])
def read_pnl_history(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    """Retrieve recorded account PnL snapshots only. Modeled ex-ante history is not returned here."""
    from app.api.deps import demo_mode_enabled

    if demo_mode_enabled():
        return get_pnl_history(account_id)

    try:
        active_id = resolve_authorized_account_id(account_id, adapter, principal)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc

    try:
        history = get_pnl_history(active_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PNL_HISTORY_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc

    if not history:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PNL_HISTORY_EMPTY",
                "message": "No recorded account PnL snapshots exist for this account.",
            },
        )
    return history


@router.post("/record", response_model=PortfolioPnLSnapshot, dependencies=[Depends(require_scope("portfolio:sync"))])
def create_pnl_snapshot(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    """Manually record a portfolio performance snapshot."""
    if account_id == "all":
        from app.api.routes.portfolio import _get_consolidated_summary_and_positions

        allowed_ids = resolve_authorized_account_ids(adapter, principal, "all")
        summary, positions = _get_consolidated_summary_and_positions(adapter, allowed_ids)
        validate_and_gate_snapshot(summary, positions)
        res = record_pnl_snapshot(summary, positions, "all")
        log_audit_action(
            action="pnl_snapshot_recorded",
            object_type="portfolio",
            object_id="all",
            actor_id=principal.user_id,
            account_id="all",
            metadata={"net_liquidation": summary.net_liquidation},
        )
        return res

    try:
        active_id = resolve_authorized_account_id(account_id, adapter, principal)
        summary = adapter.get_account_summary(active_id)
        positions = adapter.get_positions(active_id)
        validate_and_gate_snapshot(summary, positions)
        res = record_pnl_snapshot(summary, positions, active_id)
        log_audit_action(
            action="pnl_snapshot_recorded",
            object_type="portfolio",
            object_id=active_id,
            actor_id=principal.user_id,
            account_id=active_id,
            metadata={"net_liquidation": summary.net_liquidation},
        )
        return res
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
