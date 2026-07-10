from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import get_current_principal, require_scope
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.broker.ibkr_readonly import configure_runtime_ibkr, get_runtime_ibkr_config
from app.core.audit import log_audit_action


from app.core.config import settings


router = APIRouter(
    prefix="/broker",
    tags=["broker-readonly"],
    dependencies=[Depends(get_current_principal)],
)


class BrokerConfigureRequest(BaseModel):
    mode: str = "ibkr_readonly"
    host: str = "127.0.0.1"
    port: int = Field(default=4002, ge=1, le=65535)
    client_id: int = Field(default=10, ge=1, le=999999)
    account_id: Optional[str] = None


@router.get("/status")
def status(adapter: BrokerAdapter = Depends(get_broker_adapter)) -> dict[str, str]:
    return adapter.health_check()


@router.post("/configure-readonly", dependencies=[Depends(require_scope("configuration:write"))])
def configure_readonly(payload: BrokerConfigureRequest) -> dict[str, object]:
    if payload.mode not in ("ibkr_readonly", "mock_ibkr_readonly"):
        raise HTTPException(status_code=400, detail="Invalid broker mode. Must be 'ibkr_readonly' or 'mock_ibkr_readonly'.")
    if payload.host not in set(settings.allowed_ibkr_hosts):
        raise HTTPException(status_code=400, detail="IBKR host is not permitted")

    settings.broker_mode = payload.mode
    configure_runtime_ibkr(payload.host, payload.port, payload.client_id, payload.account_id)
    from app.core.persistence import update_env_file
    update_env_file({
        "BROKER_MODE": payload.mode,
        "IBKR_HOST": payload.host,
        "IBKR_PORT": str(payload.port),
        "IBKR_CLIENT_ID": str(payload.client_id),
        "IBKR_ACCOUNT_ID": payload.account_id or "",
    })
    log_audit_action(
        action="broker_configured",
        object_type="configuration",
        object_id=payload.mode,
        metadata={"host": payload.host, "port": payload.port, "client_id": payload.client_id, "account_id": payload.account_id}
    )
    config = get_runtime_ibkr_config()
    return {
        "configured": True,
        "mode": payload.mode,
        "host": config["host"],
        "port": config["port"],
        "client_id": config["client_id"],
        "account_id": config["account_id"],
        "read_only": True,
        "trading": "disabled",
    }


@router.post("/sync-readonly", dependencies=[Depends(require_scope("portfolio:sync"))])
def sync_readonly(adapter: BrokerAdapter = Depends(get_broker_adapter)) -> dict[str, object]:
    try:
        from app.services.portfolio.transaction_store import sync_transactions

        accounts = adapter.get_accounts()
        transaction_counts: dict[str, int] = {}
        coverage_reports: dict[str, object] = {}
        for account in accounts:
            synced, coverage = sync_transactions(adapter, account.id)
            transaction_counts[account.id] = len(synced)
            coverage_reports[account.id] = coverage
        return {
            "status": "synced_readonly",
            "accounts": accounts,
            "transaction_counts": transaction_counts,
            "ledger_coverage": coverage_reports,
            "trading": "disabled",
        }
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("/accounts")
def accounts(adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        return adapter.get_accounts()
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("/accounts/{account_id}/summary")
def account_summary(account_id: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        return adapter.get_account_summary(account_id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("/accounts/{account_id}/positions")
def positions(account_id: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        return adapter.get_positions(account_id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.post("/sync-flex", dependencies=[Depends(require_scope("portfolio:sync"))])
def sync_flex(account_id: str, adapter: BrokerAdapter = Depends(get_broker_adapter)) -> dict[str, object]:
    from app.core.config import settings
    from app.services.broker.flex_query import fetch_flex_cash_ledger, flex_activity_query_configured, mock_flex_transactions
    from app.services.portfolio.ledger_coverage import build_ledger_coverage, save_ledger_coverage
    from app.services.portfolio.transaction_store import load_transactions, save_transactions

    if flex_activity_query_configured():
        flex_result = fetch_flex_cash_ledger(account_id)
        merged = save_transactions(account_id, flex_result.transactions)
        coverage = build_ledger_coverage(
            account_id=account_id,
            transactions=merged,
            imported_sections=["flex_cash_ledger"] + flex_result.imported_sections,
            rejected_row_count=flex_result.rejected_row_count,
            flex_query_id=flex_result.query_id,
            flex_generated_at=flex_result.generated_at,
            flex_statement_account_id=flex_result.account_id,
            period_start=flex_result.report_period_start,
            period_end=flex_result.report_period_end,
        )
        save_ledger_coverage(coverage)
        return {
            "status": coverage.status,
            "source": "ibkr_flex_query",
            "transaction_count": len(merged),
            "rejected_row_count": flex_result.rejected_row_count,
            "ledger_coverage": coverage,
        }
    if settings.broker_mode == "mock_ibkr_readonly":
        rows = mock_flex_transactions(account_id)
        merged = save_transactions(account_id, rows)
        coverage = build_ledger_coverage(
            account_id=account_id,
            transactions=merged,
            imported_sections=["mock_flex_cash_ledger"],
        )
        save_ledger_coverage(coverage)
        return {"status": coverage.status, "source": "mock_flex_query", "transaction_count": len(merged), "ledger_coverage": coverage}

    from fastapi import HTTPException

    raise HTTPException(
        status_code=400,
        detail="IBKR Flex Query is not configured. Set IBKR_FLEX_TOKEN and IBKR_FLEX_ACTIVITY_QUERY_ID.",
    )


@router.get("/accounts/{account_id}/transactions")
def transactions(
    account_id: str,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    from app.services.portfolio.transaction_store import get_transactions as load_stored_transactions

    end_date = date.today()
    try:
        stored = load_stored_transactions(account_id, end_date - timedelta(days=365), end_date)
        if stored:
            return stored
        return adapter.get_transactions(account_id, end_date - timedelta(days=90), end_date)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
