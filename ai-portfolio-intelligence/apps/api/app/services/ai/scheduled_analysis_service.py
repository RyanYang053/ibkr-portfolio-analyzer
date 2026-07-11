from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.core.audit import log_audit_action
from app.core.config import settings
from app.schemas.domain import utc_now
from app.services.broker.base import BrokerAdapter
from app.services.system_actor import SystemActor


def _load_runs() -> list[dict[str, Any]]:
    from app.api.routes.ai import _load_runs as load_runs

    return load_runs()


def _save_runs(runs: list[dict[str, Any]]) -> None:
    from app.api.routes.ai import _save_runs as save_runs

    save_runs(runs)


def _fallback_analysis_text(period: str, net_liq: float, cash: float) -> str:
    label = {"morning": "Morning", "midday": "Midday", "night": "Night"}.get(period, "Scheduled")
    return f"""### **{label} Portfolio Data Check**

* **Portfolio Snapshot**: Net liquidation is ${net_liq:,.2f}; cash is ${cash:,.2f}.
* **Market Analysis**: Current market, technical, and catalyst data unavailable because Gemini analysis did not complete.
* **Decision Support**: No security action or price level is generated from incomplete data. Refresh after the missing data source is restored."""


def run_scheduled_analysis(
    *,
    period: str,
    authorized_account_id: str,
    adapter: BrokerAdapter,
    actor: SystemActor,
) -> dict[str, Any]:
    """Application service for scheduled portfolio analysis.

    Workers and HTTP routes must call this function instead of invoking route handlers directly.
    The caller must resolve and authorize the account before invoking this service.
    """
    from app.services.ai.client import GeminiClient

    period = period.lower().strip()
    if period not in {"morning", "midday", "night"}:
        raise ValueError("Invalid period. Must be morning, midday, or night.")

    active_id = authorized_account_id
    summary = adapter.get_account_summary(active_id)
    positions = adapter.get_positions(active_id)
    from app.services.data_quality.validation import validate_and_gate_snapshot

    validate_and_gate_snapshot(summary, positions)
    net_liq = summary.net_liquidation
    cash = summary.cash

    from app.services.portfolio.pnl_tracker import get_pnl_history

    pnl_history = get_pnl_history(active_id)[-7:]
    spy_price = 0.0
    qqq_price = 0.0
    try:
        import sys

        from app.services.market_data.mock_provider import MockMarketDataProvider

        allow_mock = (settings.broker_mode == "mock_ibkr_readonly") or ("pytest" in sys.modules)
        provider = MockMarketDataProvider(allow_mock=allow_mock)
        spy_price = provider.get_latest_price("SPY")
        qqq_price = provider.get_latest_price("QQQ")
    except Exception:
        pass

    gemini = GeminiClient()
    if gemini.configured:
        structured_payload = {
            "period": period,
            "portfolio": {
                "net_liquidation": net_liq,
                "cash": cash,
                "base_currency": summary.base_currency,
                "total_unrealized_pnl": summary.total_unrealized_pnl,
                "total_realized_pnl": summary.total_realized_pnl,
                "data_timestamp": summary.data_timestamp.isoformat(),
            },
            "market_indices": {
                "SPY": spy_price if spy_price > 0 else None,
                "QQQ": qqq_price if qqq_price > 0 else None,
            },
            "performance_history": [
                {
                    "date": entry.date,
                    "net_liquidation": entry.net_liquidation,
                    "cash": entry.cash,
                    "daily_pnl": entry.daily_pnl,
                    "daily_pnl_percent": entry.daily_pnl_percent,
                }
                for entry in pnl_history
            ],
            "holdings": [
                {
                    "symbol": pos.symbol,
                    "market_price": pos.market_price,
                    "market_value": pos.market_value,
                    "portfolio_weight": pos.portfolio_weight,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "currency": pos.currency,
                    "stock_type": pos.stock_type,
                    "is_speculative": pos.is_speculative,
                    "updated_at": pos.updated_at.isoformat(),
                }
                for pos in positions
            ],
            "excluded": ["account_id", "credentials", "open_orders", "quantity", "average_cost", "buying_power"],
        }
        prompt = json.dumps(structured_payload, indent=2, sort_keys=True)
        system_instruction = """
You are a read-only portfolio research analyst. Use only the provided structured data.
Identify data-quality, concentration, performance, and catalyst review issues.
Do not provide order types, buy/sell quantities, cash deployment amounts, or execution instructions.
Do not invent current market conditions. Clearly mark missing data and require human review.
Write a concise Markdown review with evidence from the supplied fields.
"""
        web_grounded = False
        try:
            analysis_text = gemini.generate_text(prompt, system_instruction, tools=[])
            web_grounded = gemini.last_grounding_used
        except Exception as exc:
            analysis_text = f"*(Gemini analysis error: {exc})*\n\n" + _fallback_analysis_text(period, net_liq, cash)
    else:
        web_grounded = False
        analysis_text = _fallback_analysis_text(period, net_liq, cash)

    is_demo = settings.broker_mode == "mock_ibkr_readonly"
    is_live_portfolio = not is_demo and active_id not in (
        "MOCK-001",
        "MOCK-002",
        "SYNTHETIC_RESEARCH",
        "WATCHLIST_ONLY",
        "all",
    )
    is_live_market = not is_demo
    is_mock_fallback = is_demo

    provenance_badge = (
        f"\n\n*Data Provenance: Live Portfolio: {'Yes' if is_live_portfolio else 'No'} | "
        f"Live Market: {'Yes' if is_live_market else 'No'} | "
        f"Cached: No | "
        f"Mock Fallback: {'Yes' if is_mock_fallback else 'No'} | "
        f"Web-Grounded: {'Yes' if web_grounded else 'No'}*"
    )
    analysis_text += provenance_badge

    runs = _load_runs()
    today_str = date.today().isoformat()
    runs = [
        row
        for row in runs
        if not (
            row.get("timestamp", "").startswith(today_str)
            and row.get("period") == period
            and row.get("account_id") == active_id
        )
    ]

    new_run = {
        "timestamp": utc_now().isoformat(),
        "period": period,
        "account_id": active_id,
        "actor_id": actor.actor_id,
        "net_liquidation": round(net_liq, 2),
        "cash": round(cash, 2),
        "analysis_text": analysis_text,
        "provenance": {
            "live_portfolio_data": is_live_portfolio,
            "live_market_data": is_live_market,
            "cached_data": False,
            "mock_fallback_data": is_mock_fallback,
            "web_grounded_context": web_grounded,
        },
    }
    runs.append(new_run)
    _save_runs(runs)
    log_audit_action(
        action="ai_scheduled_run",
        object_type="portfolio",
        object_id=period,
        actor_id=actor.actor_id,
        actor_type="system",
        account_id=active_id,
        metadata={"account_id": active_id, "actor_id": actor.actor_id},
    )
    return new_run
