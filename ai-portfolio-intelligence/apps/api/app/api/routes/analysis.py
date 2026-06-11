from fastapi import APIRouter, Depends

from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.scoring.decision_engine import build_recommendation


router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
def recommendations(adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        positions = adapter.get_positions(adapter.get_accounts()[0].id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
    return [build_recommendation(position) for position in positions]


@router.get("/{symbol}")
def recommendation(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        positions = adapter.get_positions(adapter.get_accounts()[0].id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
    for position in positions:
        if position.symbol == symbol.upper():
            return build_recommendation(position)
    return {"status": "not_found"}


@router.post("/generate")
def generate(adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        positions = adapter.get_positions(adapter.get_accounts()[0].id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
    return {"recommendations": [build_recommendation(position) for position in positions]}
