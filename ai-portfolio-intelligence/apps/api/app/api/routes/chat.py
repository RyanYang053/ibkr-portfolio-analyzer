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
from app.schemas.domain import Position, utc_now

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
            price = 100.0
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
        else:
            technicals = {"rsi_14": 50.0, "drawdown_from_52w_high": 0.0, "trend_classification": "neutral"}
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
        "technicals": technicals or "N/A",
        "recent_news_catalysts": news,
    }


CHAT_SYSTEM_INSTRUCTION = """
You are a professional investment research assistant for a read-only portfolio intelligence system.
Your job is to analyze securities and portfolios using the provided structured stock context (including fundamentals, technicals, news, and valuation) and answer the user's query.

Rules:
1. Ground your analysis in the provided facts. Do not invent financial data.
2. Use Google Search grounding to retrieve any extra current macroeconomic context, interest rates, or news for tagged stocks.
3. Be professional, balanced, and objective. Write your responses in clear Markdown.
4. Explain potential risks and suggestions (e.g., target buy zones, trim zones) using decision-support terms.
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
    try:
        accounts = adapter.get_accounts()
        if accounts:
            acct_id = accounts[0].id
            summary = adapter.get_account_summary(acct_id)
            positions = adapter.get_positions(acct_id)
            
            portfolio_summary_text += "Current User Portfolio State:\n"
            portfolio_summary_text += f"- Net Liquidation: ${summary.net_liquidation:,.2f} {summary.base_currency}\n"
            portfolio_summary_text += f"- Cash Balance: ${summary.cash:,.2f} {summary.base_currency}\n"
            portfolio_summary_text += f"- Buying Power: ${summary.buying_power:,.2f} {summary.base_currency}\n"
            portfolio_summary_text += f"- Margin Requirement: ${summary.margin_requirement:,.2f} {summary.base_currency}\n"
            portfolio_summary_text += "- Active Portfolio Positions:\n"
            for pos in positions:
                if pos.quantity > 0:
                    portfolio_summary_text += f"  * {pos.symbol} | Qty: {pos.quantity} | Avg Cost: ${pos.avg_cost:.2f} | Price: ${pos.market_price:.2f} | Value: ${pos.market_value:.2f} | Weight: {pos.portfolio_weight:.2f}% | Type: {pos.stock_type}\n"
            
            # Load PnL history trend
            try:
                from app.services.portfolio.pnl_tracker import get_pnl_history
                pnl_history = get_pnl_history()[-7:]
                if pnl_history:
                    portfolio_summary_text += "- Recent 7-Day Performance Trend:\n"
                    for entry in pnl_history:
                        portfolio_summary_text += f"  * {entry.date}: Net Liq: ${entry.net_liquidation:,.2f} | Cash: ${entry.cash:,.2f} | PnL: ${entry.daily_pnl:+,.2f} ({entry.daily_pnl_percent:+.2f}%)\n"
            except Exception:
                pass
                
            portfolio_summary_text += "\n"
    except Exception as exc:
        portfolio_summary_text += f"Current User Portfolio State: Unavailable ({exc})\n\n"

    gemini = GeminiClient()
    if gemini.configured:
        # 3. Build conversational prompt
        history_text = ""
        for msg in payload.history:
            role_label = "User" if msg.role == "user" else "Assistant"
            history_text += f"{role_label}: {msg.content}\n\n"

        prompt = ""
        # Inject the user's real-time cash and holdings context first
        prompt += portfolio_summary_text
        
        if tagged_contexts:
            prompt += "Tagged Stock Contexts (specifically selected by user for this message):\n"
            import json
            prompt += json.dumps(tagged_contexts, indent=2) + "\n\n"
        
        if history_text:
            prompt += f"Conversation History:\n{history_text}"
            
        prompt += f"User: {payload.message}"

        try:
            response_text = gemini.generate_text(prompt, CHAT_SYSTEM_INSTRUCTION)
            return {"response": response_text}
        except Exception as exc:
            # Fall back to deterministic mock response on API failure
            return {
                "response": f"*(Gemini API connection error: {exc})*\n\nHere is a local deterministic research overview for the requested symbols:\n\n" + _fallback_chat_response(payload.message, tagged_contexts, portfolio_summary_text)
            }

    # 4. Fallback when Gemini is not configured
    return {
        "response": "*(Demo mode active: Gemini key not configured)*\n\nHere is a local deterministic research overview for your query:\n\n" + _fallback_chat_response(payload.message, tagged_contexts, portfolio_summary_text)
    }


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
    lines.append("Based on your portfolio cash levels and technical support indicators, compare suggested entry ranges for any tagged symbols before making investment decisions. The system is read-only and does not execute trades.")
    
    return "\n".join(lines)

