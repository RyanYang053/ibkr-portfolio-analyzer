from fastapi import HTTPException

from app.core.config import settings
from app.services.broker.base import BrokerAdapter
from app.services.broker.ibkr_readonly import IBKRReadOnlyAdapter
from app.services.broker.mock_ibkr import MockIBKRAdapter


def get_broker_adapter() -> BrokerAdapter:
    if settings.broker_mode == "mock_ibkr_readonly":
        return MockIBKRAdapter()
    return IBKRReadOnlyAdapter()


def broker_not_configured_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "BROKER_NOT_CONFIGURED",
            "message": str(exc),
            "next_step": "Connect a read-only IBKR local gateway or explicitly enable demo mode with BROKER_MODE=mock_ibkr_readonly.",
            "trading": "disabled",
        },
    )


def data_provider_not_configured_error(provider: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "DATA_PROVIDER_NOT_CONFIGURED",
            "message": f"{provider} provider is not configured. Mock data is disabled by default.",
            "next_step": "Connect a real data provider or explicitly enable demo mode with BROKER_MODE=mock_ibkr_readonly.",
        },
    )


def demo_mode_enabled() -> bool:
    return settings.broker_mode == "mock_ibkr_readonly"
