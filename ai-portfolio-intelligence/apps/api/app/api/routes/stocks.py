from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.account_deps import resolve_authorized_account_id, resolve_authorized_account_ids
from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import broker_not_configured_error, data_provider_not_configured_error, demo_mode_enabled, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import find_portfolio_position, is_symbol_held
from app.services.portfolio.snapshot import gate_professional_response, is_portfolio_position
from app.services.fundamentals.providers import get_fundamental_provider
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from app.services.technicals.indicators import calculate_technical_indicators
from app.services.tenant_scope import tenant_user_id


router = APIRouter(
    prefix="/stocks",
    tags=["stocks"],
    dependencies=[Depends(get_current_principal)],
)


def _authorized_position(
    symbol: str,
    adapter: BrokerAdapter,
    principal: Principal,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
):
    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    position = find_portfolio_position(symbol, adapter, active_id, con_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found in accessible account")
    return position


def _research_position(symbol: str, principal: Principal):
    """Synthetic watchlist/research position. Never reads broker account data."""
    from app.services.watchlist_store import symbol_on_user_watchlist
    from app.services.broker.securities import classify_security
    from app.schemas.domain import Position, utc_now
    from app.core.config import settings

    sym = symbol.upper().strip()
    if not symbol_on_user_watchlist(sym, tenant_user_id(principal)):
        raise HTTPException(status_code=404, detail=f"Stock data not found for {sym}")

    sec_info = classify_security(sym)
    allow_mock = settings.broker_mode == "mock_ibkr_readonly"
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
        updated_at=utc_now(),
    )


def _resolve_position(
    symbol: str,
    adapter: BrokerAdapter,
    principal: Principal,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
):
    if account_id is not None or con_id is not None:
        return _authorized_position(symbol, adapter, principal, account_id, con_id)
    try:
        for active_id in resolve_authorized_account_ids(adapter, principal, "all"):
            position = find_portfolio_position(symbol, adapter, active_id, con_id)
            if position is not None:
                return position
    except HTTPException as exc:
        if exc.status_code not in {403, 404, 422, 503}:
            raise
    except Exception:
        pass
    return _research_position(symbol, principal)


def _is_held(
    symbol: str,
    adapter: BrokerAdapter,
    principal: Principal,
    account_id: Optional[str] = None,
) -> bool:
    try:
        if account_id is not None:
            active_id = resolve_authorized_account_id(account_id, adapter, principal)
            if is_symbol_held(symbol, adapter, active_id):
                return True
        for active_id in resolve_authorized_account_ids(adapter, principal, "all"):
            if is_symbol_held(symbol, adapter, active_id):
                return True
    except HTTPException:
        raise
    except Exception:
        pass

    from app.services.watchlist_store import symbol_on_user_watchlist

    return symbol_on_user_watchlist(symbol.upper(), tenant_user_id(principal))


@router.get("/{symbol}")
def stock(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    return _resolve_position(symbol, adapter, principal, account_id, con_id)


@router.get("/{symbol}/fundamentals")
def fundamentals(
    symbol: str,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter, principal, account_id):
        raise data_provider_not_configured_error("Fundamental")
    allow_mock = is_demo
    try:
        return get_fundamental_provider(allow_mock=allow_mock).get_fundamentals(symbol.upper())
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Fundamental data not found for {symbol.upper()}: {exc}") from exc


@router.get("/{symbol}/technicals")
def technicals(
    symbol: str,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter, principal, account_id):
        raise data_provider_not_configured_error("Technical")
    allow_mock = is_demo
    provider = MockMarketDataProvider(allow_mock=allow_mock)
    try:
        bars = provider.get_chart_data(symbol.upper(), "1y", "1d")
        closes = [float(item["close"]) for item in bars if item.get("close") is not None]
        from app.services.technicals.indicators import calculate_technical_indicators_from_bars

        if len(closes) < 252:
            raise RuntimeError("At least 252 daily closes are required")
        indicators = calculate_technical_indicators_from_bars(symbol.upper(), bars)
        historical_prices = closes[-30:]
        has_volume = any(bar.get("volume") not in (None, 0) for bar in bars)
        data_quality = "verified_close_only"
        if indicators.atr_14 is not None:
            data_quality = "verified_ohlcv_partial"
        if has_volume and indicators.atr_14 is not None:
            data_quality = "verified_ohlcv"
        if is_demo:
            data_quality = "mock_demo"
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Technical data not found for {symbol.upper()}: {exc}") from exc
    return {
        "symbol": symbol.upper(),
        "historical_prices": historical_prices,
        "rsi_14": indicators.rsi_14,
        "drawdown_from_52w_high": indicators.drawdown_from_52w_high,
        "trend_classification": indicators.trend_classification,
        "atr_14": indicators.atr_14,
        "data_quality": data_quality,
        "methodology": "Close-based trend/RSI/MACD metrics; ATR requires OHLCV bars.",
    }


@router.get("/{symbol}/chart")
def chart(
    symbol: str,
    range: str = "1Y",
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter, principal, account_id):
        raise data_provider_not_configured_error("Chart")
    range_map = {"1D": "1d", "1M": "1mo", "3M": "3mo", "1Y": "1y"}
    interval_map = {"1D": "5m", "1M": "1d", "3M": "1d", "1Y": "1d"}

    r_val = range_map.get(range.upper(), "1y")
    i_val = interval_map.get(range.upper(), "1d")
    allow_mock = is_demo
    try:
        return MockMarketDataProvider(allow_mock=allow_mock).get_chart_data(symbol, r_val, i_val)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Chart data not found for {symbol.upper()}: {exc}") from exc


@router.get("/{symbol}/valuation")
def valuation(
    symbol: str,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.broker.securities import classify_security
    from app.services.fundamentals.providers import build_scenario_valuation

    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter, principal, account_id):
        raise data_provider_not_configured_error("Valuation")
    allow_mock = is_demo
    sec_info = classify_security(symbol.upper())
    market_price = None
    if _is_held(symbol, adapter, principal, account_id):
        position = _authorized_position(symbol, adapter, principal, account_id)
        market_price = position.market_price
    try:
        result = build_scenario_valuation(
            symbol.upper(),
            sector=sec_info.get("sector", "Unknown"),
            stock_type=sec_info.get("stock_type", "universal"),
            market_price=market_price,
            allow_mock=allow_mock,
        )
        if result is None:
            raise ValueError("valuation inputs unavailable")
        return result
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Valuation data not found for {symbol.upper()}: {exc}") from exc


@router.get("/{symbol}/xbrl-facts")
def xbrl_facts(
    symbol: str,
    company_type: str = "general_operating",
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.fundamentals.providers.edgar_provider import extract_xbrl_facts

    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter, principal, account_id):
        raise data_provider_not_configured_error("XBRL facts")
    if is_demo:
        return {
            "symbol": symbol.upper(),
            "company_type": company_type,
            "facts": [],
            "source": "mock_demo",
            "synthetic_demo": True,
        }
    facts = extract_xbrl_facts(symbol.upper(), company_type=company_type)
    if not facts:
        raise HTTPException(status_code=404, detail=f"XBRL facts not found for {symbol.upper()}")
    return {
        "symbol": symbol.upper(),
        "company_type": company_type,
        "facts": facts,
        "source": "sec_edgar_companyfacts",
        "synthetic_demo": False,
    }


@router.get("/{symbol}/news")
def news(
    symbol: str,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    is_demo = demo_mode_enabled()
    if not is_demo and not _is_held(symbol, adapter, principal, account_id):
        raise data_provider_not_configured_error("News/catalyst")
    allow_mock = is_demo
    try:
        return MockMarketDataProvider(allow_mock=allow_mock).get_recent_news(symbol)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"News data not found for {symbol.upper()}: {exc}") from exc


@router.get("/{symbol}/score")
def score(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    position = _resolve_position(symbol, adapter, principal, account_id, con_id)
    result = score_stock(position)
    if is_portfolio_position(position):
        active_id = resolve_authorized_account_id(account_id or position.account_id, adapter, principal)
        return gate_professional_response(adapter, principal, active_id, result)
    return result


@router.get("/{symbol}/analysis")
def analysis(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    position = _resolve_position(symbol, adapter, principal, account_id, con_id)
    from app.services.ai.report_cache import get_cached_report

    cache_account = position.account_id if is_portfolio_position(position) else "watchlist"
    cached = get_cached_report(position.symbol, user_id=tenant_user_id(principal), account_id=cache_account)
    if cached:
        cached = dict(cached)
        if "provenance" in cached:
            prov = dict(cached["provenance"])
            prov["cached_data"] = True
            cached["provenance"] = prov
    score = score_stock(position)
    payload = {
        "position": position.model_dump(),
        "score": score.model_dump(),
        "recommendation": build_recommendation(position).model_dump(),
        "last_ai_report": cached,
    }
    if is_portfolio_position(position):
        active_id = resolve_authorized_account_id(account_id or position.account_id, adapter, principal)
        return gate_professional_response(adapter, principal, active_id, payload)
    return payload


@router.get("/{symbol}/options-strategy")
def options_strategy(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    position = _authorized_position(symbol, adapter, principal, account_id, con_id)
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

    try:
        active_id = resolve_authorized_account_id(account_id, adapter, principal)
        summary_data = adapter.get_account_summary(active_id)
        cash_available = summary_data.cash
        accounts = adapter.get_accounts()
        account_type = next((acct.account_type for acct in accounts if acct.id == active_id), "Margin")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "ACCOUNT_CONTEXT_UNAVAILABLE",
                "message": "Options eligibility requires a resolved broker account context.",
                "error": str(exc),
            },
        ) from exc

    from app.services.ai.report_generator import generate_options_strategy_report
    result = generate_options_strategy_report(
        position,
        technicals_data,
        cash_available=cash_available,
        account_type=account_type,
    )
    return gate_professional_response(adapter, principal, active_id, result)
