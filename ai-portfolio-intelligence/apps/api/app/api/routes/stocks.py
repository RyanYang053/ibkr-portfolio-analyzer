from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import broker_not_configured_error, data_provider_not_configured_error, demo_mode_enabled, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from app.services.technicals.indicators import calculate_technical_indicators


router = APIRouter(prefix="/stocks", tags=["stocks"])


def _position(symbol: str, adapter: BrokerAdapter):
    try:
        accounts = adapter.get_accounts()
        if accounts:
            positions = adapter.get_positions(accounts[0].id)
            for position in positions:
                if position.symbol.upper() == symbol.upper():
                    return position
    except Exception:
        pass
        
    # Fallback: create synthetic position for watchlist / non-held stocks
    from app.services.broker.securities import classify_security
    from app.schemas.domain import Position, utc_now
    from app.core.config import settings
    
    sym = symbol.upper().strip()
    sec_info = classify_security(sym)
    
    allow_mock = (settings.broker_mode == "mock_ibkr_readonly")
    try:
        price = MockMarketDataProvider(allow_mock=allow_mock).get_latest_price(sym)
    except Exception as exc:
        if not allow_mock:
            raise HTTPException(status_code=404, detail=f"Stock data not found for {sym}") from exc
        price = 0.0
        
    return Position(
        account_id="WATCHLIST_ONLY",
        symbol=sym,
        company_name=sec_info["company_name"],
        asset_class=sec_info["asset_class"],
        quantity=0.0,
        avg_cost=0.0,
        market_price=price,
        market_value=0.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        currency=sec_info["currency"],
        exchange=sec_info["exchange"],
        sector=sec_info["sector"],
        industry=sec_info["industry"],
        portfolio_weight=0.0,
        stock_type=sec_info["stock_type"],
        is_etf=sec_info["is_etf"],
        is_speculative=sec_info["is_speculative"],
        updated_at=utc_now()
    )


def _is_held(symbol: str, adapter: BrokerAdapter) -> bool:
    try:
        accounts = adapter.get_accounts()
        if accounts:
            positions = adapter.get_positions(accounts[0].id)
            if any(p.symbol.upper() == symbol.upper() for p in positions):
                return True
    except Exception:
        pass
        
    # Check watchlist
    from app.api.routes.watchlist import _WATCHLIST
    if any(item["symbol"].upper() == symbol.upper() for item in _WATCHLIST):
        return True
        
    return False



@router.get("/{symbol}")
def stock(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    return _position(symbol, adapter)


@router.get("/{symbol}/fundamentals")
def fundamentals(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter):
        raise data_provider_not_configured_error("Fundamental")
    allow_mock = is_demo
    try:
        return MockFundamentalProvider(allow_mock=allow_mock).get_fundamentals(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Fundamental data not found for {symbol.upper()}: {exc}")


@router.get("/{symbol}/technicals")
def technicals(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter):
        raise data_provider_not_configured_error("Technical")
    allow_mock = is_demo
    provider = MockMarketDataProvider(allow_mock=allow_mock)
    try:
        history = provider.get_historical_prices(symbol.upper(), date.today() - timedelta(days=260), date.today())
        historical_prices = [item["close"] for item in history[-30:]]
        
        from app.services.technicals.indicators import calculate_technical_indicators
        closes = [item["close"] for item in history]
        if len(closes) >= 200:
            indicators = calculate_technical_indicators(symbol.upper(), closes)
            rsi = indicators.rsi_14
            drawdown = indicators.drawdown_from_52w_high
            trend = indicators.trend_classification
        else:
            raise RuntimeError("At least 200 daily closes are required")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Technical data not found for {symbol.upper()}: {exc}")
    return {
        "symbol": symbol.upper(),
        "historical_prices": historical_prices,
        "rsi_14": rsi,
        "drawdown_from_52w_high": drawdown,
        "trend_classification": trend,
        "data_quality": "verified" if not is_demo else "mock_demo",
    }



@router.get("/{symbol}/chart")
def chart(symbol: str, range: str = "1Y", adapter: BrokerAdapter = Depends(get_broker_adapter)):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter):
        raise data_provider_not_configured_error("Chart")
    range_map = {"1D": "1d", "1M": "1mo", "3M": "3mo", "1Y": "1y"}
    interval_map = {"1D": "5m", "1M": "1d", "3M": "1d", "1Y": "1d"}
    
    r_val = range_map.get(range.upper(), "1y")
    i_val = interval_map.get(range.upper(), "1d")
    allow_mock = is_demo
    try:
        return MockMarketDataProvider(allow_mock=allow_mock).get_chart_data(symbol, r_val, i_val)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Chart data not found for {symbol.upper()}: {exc}")


@router.get("/{symbol}/valuation")
def valuation(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):

    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter):
        raise data_provider_not_configured_error("Valuation")
    allow_mock = is_demo
    try:
        data = MockFundamentalProvider(allow_mock=allow_mock).get_fundamentals(symbol.upper())
        return {"symbol": symbol.upper(), "pe_forward": data.pe_forward, "ev_sales": data.ev_sales, "fcf_yield": data.fcf_yield}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Valuation data not found for {symbol.upper()}: {exc}")


@router.get("/{symbol}/news")
def news(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter):
        raise data_provider_not_configured_error("News/catalyst")
    allow_mock = is_demo
    try:
        return MockMarketDataProvider(allow_mock=allow_mock).get_recent_news(symbol)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"News data not found for {symbol.upper()}: {exc}")
        raise HTTPException(status_code=404, detail=f"News data not found for {symbol.upper()}: {exc}")



@router.get("/{symbol}/score")
def score(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    return score_stock(_position(symbol, adapter))


@router.get("/{symbol}/analysis")
def analysis(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    position = _position(symbol, adapter)
    from app.services.ai.report_cache import get_cached_report
    cached = get_cached_report(position.symbol)
    if cached:
        cached = dict(cached)
        if "provenance" in cached:
            prov = dict(cached["provenance"])
            prov["cached_data"] = True
            cached["provenance"] = prov
    return {
        "position": position,
        "score": score_stock(position),
        "recommendation": build_recommendation(position),
        "last_ai_report": cached,
    }


@router.get("/{symbol}/options-strategy")
def options_strategy(symbol: str, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    position = _position(symbol, adapter)
    is_demo = demo_mode_enabled()
    allow_mock = is_demo
    provider = MockMarketDataProvider(allow_mock=allow_mock)
    technicals_data = None
    try:
        history = provider.get_historical_prices(symbol.upper(), date.today() - timedelta(days=260), date.today())
        closes = [item["close"] for item in history]
        if len(closes) >= 200:
            indicators = calculate_technical_indicators(symbol.upper(), closes)
            technicals_data = {
                "trend_classification": indicators.trend_classification,
                "rsi_14": indicators.rsi_14,
                "drawdown_from_52w_high": indicators.drawdown_from_52w_high,
            }
    except Exception:
        pass

    cash_available = 15000.0
    account_type = "Margin"
    try:
        accounts = adapter.get_accounts()
        if accounts:
            summary_data = adapter.get_account_summary(accounts[0].id)
            cash_available = summary_data.cash
            account_type = accounts[0].account_type
    except Exception:
        pass

    from app.services.ai.report_generator import generate_options_strategy_report
    return generate_options_strategy_report(
        position, 
        technicals_data, 
        cash_available=cash_available, 
        account_type=account_type
    )


