from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.broker.ibkr_readonly import configure_runtime_ibkr, get_runtime_ibkr_config
from app.core.audit import log_audit_action


from app.core.config import settings


router = APIRouter(prefix="/broker", tags=["broker-readonly"])


class BrokerConfigureRequest(BaseModel):
    mode: str = "ibkr_readonly"
    host: str = "127.0.0.1"
    port: int = Field(default=4002, ge=1, le=65535)
    client_id: int = Field(default=10, ge=1, le=999999)
    account_id: Optional[str] = None


@router.get("/status")
def status(adapter: BrokerAdapter = Depends(get_broker_adapter)) -> dict[str, str]:
    return adapter.health_check()


@router.post("/configure-readonly")
def configure_readonly(payload: BrokerConfigureRequest) -> dict[str, object]:
    if payload.mode not in ("ibkr_readonly", "mock_ibkr_readonly"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid broker mode. Must be 'ibkr_readonly' or 'mock_ibkr_readonly'.")

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


@router.post("/sync-readonly")
def sync_readonly(adapter: BrokerAdapter = Depends(get_broker_adapter)) -> dict[str, object]:
    try:
        accounts = adapter.get_accounts()
        return {"status": "synced_readonly", "accounts": accounts, "trading": "disabled"}
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


@router.get("/accounts/{account_id}/transactions")
def transactions(account_id: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    end_date = date.today()
    try:
        return adapter.get_transactions(account_id, end_date - timedelta(days=90), end_date)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
