from __future__ import annotations

from typing import Any, Optional
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_broker_adapter, demo_mode_enabled
from app.services.broker.base import BrokerAdapter
from app.services.broker.securities import classify_security
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.technicals.indicators import calculate_technical_indicators
from app.services.ai.client import GeminiClient
from app.schemas.domain import Position, utc_now, InvestorProfile, InvestmentPolicyStatement

router = APIRouter(prefix="/ai/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str  # "user" or "model"
    content: str


class ChatRequest(BaseModel):
    message: str
    tagged_symbols: list[str]
    history: list[ChatMessage]


def _get_stock_context(symbol: str, adapter: BrokerAdapter) -> dict[str, Any]:
    sym = symbol.upper().strip()
    
    # 1. Fetch or build synthetic position
    position = None
    try:
        accounts = adapter.get_accounts()
        if accounts:
            positions = adapter.get_positions(accounts[0].id)
            for pos in positions:
                if pos.symbol.upper() == sym:
                    position = pos
                    break
    except Exception:
        pass

    if position is None:
        sec_info = classify_security(sym)
        try:
            price = MockMarketDataProvider().get_latest_price(sym)
        except Exception:
            price = 0.0
        position = Position(
            account_id="SYNTHETIC_RESEARCH",
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

    # 2. Fetch fundamentals
    fundamentals = None
    try:
        fundamentals = MockFundamentalProvider().get_fundamentals(sym)
    except Exception:
        pass

    # 3. Fetch technicals
    technicals = None
    try:
        history = MockMarketDataProvider().get_historical_prices(sym, date.today() - timedelta(days=260), date.today())
        closes = [item["close"] for item in history]
        if len(closes) >= 200:
            indicators = calculate_technical_indicators(sym, closes)
            technicals = {
                "rsi_14": indicators.rsi_14,
                "drawdown_from_52w_high": indicators.drawdown_from_52w_high,
                "trend_classification": indicators.trend_classification,
            }
    except Exception:
        pass

    # 4. Fetch news
    news = []
    try:
        news_data = MockMarketDataProvider().get_recent_news(sym)
        news = [
            {"title": item["title"], "publisher": item.get("source", "Yahoo Finance")}
            for item in news_data[:3]
        ]
    except Exception:
        pass

    return {
        "symbol": sym,
        "company_name": position.company_name,
        "price": position.market_price,
        "portfolio_weight": f"{position.portfolio_weight:.2f}%",
        "stock_type": position.stock_type,
        "is_speculative": position.is_speculative,
        "fundamentals": {
            "revenue_growth_yoy": f"{fundamentals.revenue_growth_yoy*100:.1f}%" if fundamentals else "N/A",
            "gross_margin": f"{fundamentals.gross_margin*100:.1f}%" if fundamentals else "N/A",
            "pe_forward": fundamentals.pe_forward if fundamentals else "N/A",
            "fcf_yield": f"{fundamentals.fcf_yield*100:.2f}%" if fundamentals and fundamentals.fcf_yield else "N/A",
        } if fundamentals else "N/A",
        "fundamentals_source": fundamentals.source if fundamentals else "missing",
        "technicals": technicals or "N/A",
        "recent_news_catalysts": news,
        "data_quality": {
            "price_missing": position.market_price <= 0,
            "fundamentals_missing": fundamentals is None,
            "technicals_missing": technicals is None,
            "catalysts_missing": not news,
        },
    }


CHAT_SYSTEM_INSTRUCTION = """
You are a professional investment research assistant for a read-only portfolio intelligence system.
Your job is to analyze securities and portfolios using the provided structured stock context (including fundamentals, technicals, news, and valuation) and answer the user's query.

Rules:
1. Ground your analysis in the provided facts. Do not invent financial data.
2. Do not use outside facts or infer missing market conditions.
3. Be professional, balanced, and objective. Write your responses in clear Markdown.
4. Do not provide order types, buy/sell quantities, cash deployment amounts, or execution instructions.
5. Remind the user that the system is read-only, does not place orders, and requires human review.
"""


@router.post("")
def chat(payload: ChatRequest, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    # 1. Gather contexts for tagged stocks
    tagged_contexts = []
    for symbol in payload.tagged_symbols:
        try:
            context = _get_stock_context(symbol, adapter)
            tagged_contexts.append(context)
        except Exception:
            pass

    # 2. Gather user's real-time portfolio summary and cash situation
    portfolio_summary_text = ""
    portfolio_context: dict[str, Any] = {
        "status": "unavailable",
        "reason": "Broker portfolio data was not available.",
    }
    try:
        accounts = adapter.get_accounts()
        if accounts:
            acct_id = accounts[0].id
            summary = adapter.get_account_summary(acct_id)
            positions = adapter.get_positions(acct_id)
            portfolio_context = {
                "status": "available",
                "summary": {
                    "net_liquidation": summary.net_liquidation,
                    "cash": summary.cash,
                    "base_currency": summary.base_currency,
                    "total_unrealized_pnl": summary.total_unrealized_pnl,
                    "total_realized_pnl": summary.total_realized_pnl,
                    "data_timestamp": summary.data_timestamp.isoformat(),
                },
                "positions": [
                    {
                        "symbol": pos.symbol,
                        "market_price": pos.market_price,
                        "market_value": pos.market_value,
                        "portfolio_weight": pos.portfolio_weight,
                        "stock_type": pos.stock_type,
                        "is_speculative": pos.is_speculative,
                        "currency": pos.currency,
                        "updated_at": pos.updated_at.isoformat(),
                    }
                    for pos in positions
                    if pos.quantity > 0
                ],
                "performance_history": [],
                "suitability": None,
            }
            
            portfolio_summary_text += "Current User Portfolio State:\n"
            portfolio_summary_text += f"- Net Liquidation: ${summary.net_liquidation:,.2f} {summary.base_currency}\n"
            portfolio_summary_text += f"- Cash Balance: ${summary.cash:,.2f} {summary.base_currency}\n"
            portfolio_summary_text += "- Active Portfolio Positions:\n"
            for pos in positions:
                if pos.quantity > 0:
                    portfolio_summary_text += f"  * {pos.symbol} | Price: ${pos.market_price:.2f} | Value: ${pos.market_value:.2f} | Weight: {pos.portfolio_weight:.2f}% | Type: {pos.stock_type}\n"
            
            # Load PnL history trend
            try:
                from app.services.portfolio.pnl_tracker import get_pnl_history
                pnl_history = get_pnl_history(acct_id)[-7:]
                if pnl_history:
                    portfolio_context["performance_history"] = [
                        {
                            "date": entry.date,
                            "net_liquidation": entry.net_liquidation,
                            "cash": entry.cash,
                            "daily_pnl": entry.daily_pnl,
                            "daily_pnl_percent": entry.daily_pnl_percent,
                        }
                        for entry in pnl_history
                    ]
                    portfolio_summary_text += "- Recent 7-Day Performance Trend:\n"
                    for entry in pnl_history:
                        portfolio_summary_text += f"  * {entry.date}: Net Liq: ${entry.net_liquidation:,.2f} | Cash: ${entry.cash:,.2f} | PnL: ${entry.daily_pnl:+,.2f} ({entry.daily_pnl_percent:+.2f}%)\n"
            except Exception:
                pass

            try:
                from app.services.suitability.engine import get_investor_profile, check_position_suitability
                from app.services.policy.engine import get_portfolio_policy, analyze_policy_drift
                
                profile = get_investor_profile(acct_id)
                policy = get_portfolio_policy(acct_id)
                drift = analyze_policy_drift(positions, summary.cash, summary.net_liquidation, policy)
                
                suitability_warnings = []
                for pos in positions:
                    suitability_warnings.extend(check_position_suitability(profile, pos))
                portfolio_context["suitability"] = {
                    "investor_profile": {
                        "objective": profile.objective,
                        "risk_tolerance": profile.risk_tolerance,
                        "risk_capacity": profile.risk_capacity,
                        "time_horizon_years": profile.time_horizon_years,
                        "account_type": profile.account_type,
                        "liquidity_needs": profile.liquidity_needs,
                        "restrictions": profile.restrictions,
                    },
                    "target_policy": {
                        "target_equity_percent": policy.target_equity_percent,
                        "target_cash_percent": policy.target_cash_percent,
                        "target_bond_percent": policy.target_bond_percent,
                        "minimum_cash": policy.minimum_cash,
                    },
                    "policy_drift": drift,
                    "warnings": suitability_warnings,
                }
                    
                portfolio_summary_text += "\nInvestor Profile & Policy IPS:\n"
                portfolio_summary_text += f"- Objective: {profile.objective} | Risk Tolerance: {profile.risk_tolerance} | Time Horizon: {profile.time_horizon_years} years | Account: {profile.account_type}\n"
                portfolio_summary_text += f"- Target Equity: {policy.target_equity_percent}% | Target Cash: {policy.target_cash_percent}% | Target Bond: {policy.target_bond_percent}%\n"
                portfolio_summary_text += f"- Policy Drift: Equity drift: {drift['drifts']['equity']['drift']:.2f}%, Cash drift: {drift['drifts']['cash']['drift']:.2f}%\n"
                portfolio_summary_text += f"- Cash Floor Check: {'OK' if summary.cash >= policy.minimum_cash else 'BELOW MINIMUM FLOOR'}\n"
                portfolio_summary_text += f"- Suitability Warnings: {'; '.join(suitability_warnings) or 'None'}\n"
            except Exception as exc:
                portfolio_summary_text += f"\nError loading professional metrics: {exc}\n"
                
            portfolio_summary_text += "\n"
    except Exception as exc:
        portfolio_summary_text += f"Current User Portfolio State: Unavailable ({exc})\n\n"
        portfolio_context = {
            "status": "unavailable",
            "reason": str(exc),
        }

    from app.core.config import settings
    is_demo = (settings.broker_mode == "mock_ibkr_readonly")
    is_live_portfolio = not is_demo and portfolio_context.get("status") == "available"
    
    # Check if tagged contexts used live market data
    if tagged_contexts:
        is_live_market = any(
            ctx.get("fundamentals_source") == "live_yahoo_finance"
            or not ctx.get("data_quality", {}).get("price_missing", True)
            for ctx in tagged_contexts
        )
    else:
        is_live_market = is_live_portfolio and any(
            position.get("market_price", 0) > 0
            for position in portfolio_context.get("positions", [])
        )
        
    is_mock_fallback = is_demo

    gemini = GeminiClient()
    if gemini.configured:
        # Gemini receives a single structured payload with no broker identifiers,
        # credentials, order data, quantities, or average costs.
        import json

        prompt = json.dumps(
            {
                "user_query": payload.message,
                "conversation_history": [
                    {"role": msg.role, "content": msg.content}
                    for msg in payload.history
                ],
                "portfolio": portfolio_context,
                "tagged_stock_contexts": tagged_contexts,
                "data_boundary": {
                    "structured_data_only": True,
                    "broker_credentials_excluded": True,
                    "account_identifiers_excluded": True,
                    "order_data_excluded": True,
                    "position_quantities_excluded": True,
                    "average_costs_excluded": True,
                    "external_search_disabled": True,
                },
            },
            indent=2,
            sort_keys=True,
        )

        try:
            response_text = gemini.generate_text(prompt, CHAT_SYSTEM_INSTRUCTION)
            web_grounded = gemini.last_grounding_used
            provenance = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": web_grounded
            }
            provenance_badge = (
                f"\n\n⚡ *Data Provenance: Live Portfolio: {'Yes' if is_live_portfolio else 'No'} | "
                f"Live Market: {'Yes' if is_live_market else 'No'} | "
                f"Cached: No | "
                f"Mock Fallback: {'Yes' if is_mock_fallback else 'No'} | "
                f"Web-Grounded: {'Yes' if web_grounded else 'No'}*"
            )
            return {"response": response_text + provenance_badge, "provenance": provenance}
        except Exception as exc:
            provenance = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_demo,
                "web_grounded_context": False
            }
            response_text = f"*(Gemini API connection error: {exc})*\n\nHere is a local deterministic research overview for the requested symbols:\n\n" + _fallback_chat_response(payload.message, tagged_contexts, portfolio_summary_text)
            provenance_badge = (
                f"\n\n⚡ *Data Provenance: Live Portfolio: {'Yes' if is_live_portfolio else 'No'} | "
                f"Live Market: {'Yes' if is_live_market else 'No'} | "
                f"Cached: No | "
                f"Mock Fallback: {'Yes' if is_demo else 'No'} | "
                f"Web-Grounded: No*"
            )
            return {"response": response_text + provenance_badge, "provenance": provenance}

    # 4. Fallback when Gemini is not configured
    provenance = {
        "live_portfolio_data": is_live_portfolio,
        "live_market_data": is_live_market,
        "cached_data": False,
        "mock_fallback_data": is_demo,
        "web_grounded_context": False
    }
    response_text = "*(Gemini is not configured; using deterministic analysis only.)*\n\nHere is a local deterministic research overview for your query:\n\n" + _fallback_chat_response(payload.message, tagged_contexts, portfolio_summary_text)
    provenance_badge = (
        f"\n\n⚡ *Data Provenance: Live Portfolio: {'Yes' if is_live_portfolio else 'No'} | "
        f"Live Market: {'Yes' if is_live_market else 'No'} | "
        f"Cached: No | "
        f"Mock Fallback: {'Yes' if is_demo else 'No'} | "
        f"Web-Grounded: No*"
    )
    return {"response": response_text + provenance_badge, "provenance": provenance}


def _fallback_chat_response(user_query: str, contexts: list[dict[str, Any]], portfolio_summary_text: str = "") -> str:
    lines = []
    
    if portfolio_summary_text:
        lines.append("### **Portfolio Situation**")
        # Format the portfolio summary cleanly for markdown
        for p_line in portfolio_summary_text.split("\n"):
            if p_line.strip():
                lines.append(p_line)
        lines.append("")

    if contexts:
        lines.append("### **Tagged Security Contexts**")
        for ctx in contexts:
            lines.append(f"#### **{ctx['symbol']} · {ctx['company_name']}**")
            lines.append(f"- **Current price**: ${ctx['price']:.2f} (Weight: {ctx['portfolio_weight']})")
            lines.append(f"- **Stock type**: {ctx['stock_type']} (Speculative: {ctx['is_speculative']})")
            
            if ctx["fundamentals"] != "N/A":
                f = ctx["fundamentals"]
                lines.append(f"- **Key Metrics**: YoY Revenue Growth: {f['revenue_growth_yoy']}, Gross Margin: {f['gross_margin']}, Forward P/E: {f['pe_forward']}, FCF Yield: {f['fcf_yield']}")
                
            if ctx["technicals"] != "N/A":
                t = ctx["technicals"]
                lines.append(f"- **Technicals**: Trend is {t['trend_classification']} | RSI (14) is {t['rsi_14']:.1f} | 52W Drawdown is {t['drawdown_from_52w_high']:.1f}%")
                
            if ctx["recent_news_catalysts"]:
                lines.append("- **Recent News Headlines**:")
                for item in ctx["recent_news_catalysts"]:
                    lines.append(f"  * *\"{item['title']}\"* ({item['publisher']})")
            lines.append("")
    else:
        lines.append("*I can help you analyze specific stocks. Tag symbols using the tag button or header box to feed their latest metrics and news sentiment into the chat contexts!*")
        lines.append("")

    lines.append("---")
    lines.append("**Decision Support Suggestion**:")
    lines.append("Review the supplied evidence, missing-data flags, and portfolio concentration before making any investment decision. The system is read-only and does not execute trades.")
    
    return "\n".join(lines)
