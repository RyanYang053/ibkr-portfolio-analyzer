from __future__ import annotations

from datetime import date, datetime
import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from app.api.routes import ai as ai_routes
from app.api.routes.pnl import create_pnl_snapshot
from app.schemas.domain import AccountSummary, Position, utc_now
from app.services.ai.client import GeminiClient
from app.services.ai.prompt_templates import build_portfolio_memo_prompt
from app.services.ai.structured_outputs import build_structured_stock_context
from app.services.ai.thesis_tracker import evaluate_thesis
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.guardrails.engine import append_compliance_disclaimer
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.risk.advanced_risk import calculate_advanced_risk_metrics
from app.services.attribution.engine import calculate_performance_attribution
from app.services.broker.ibkr_readonly import _ensure_sync_event_loop, get_exchange_rate
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from app.services import scheduler


def _position() -> Position:
    return Position(
        account_id="U1234567",
        symbol="AMZN",
        company_name="Amazon.com, Inc.",
        asset_class="STK",
        quantity=100,
        avg_cost=180,
        market_price=220,
        market_value=22_000,
        unrealized_pnl=4_000,
        currency="USD",
        exchange="SMART",
        sector="Consumer Cyclical",
        industry="Internet Retail",
        portfolio_weight=12,
        stock_type="core",
        updated_at=utc_now(),
    )


def _summary() -> AccountSummary:
    return AccountSummary(
        account_id="U1234567",
        net_liquidation=100_000,
        cash=20_000,
        buying_power=40_000,
        margin_requirement=0,
        excess_liquidity=40_000,
        total_unrealized_pnl=4_000,
        total_realized_pnl=0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )


class _FailedHTTPClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        raise httpx.ConnectError("offline")


def test_live_market_provider_never_fabricates_price_or_news(monkeypatch):
    monkeypatch.setattr(httpx, "Client", _FailedHTTPClient)
    provider = MockMarketDataProvider(allow_mock=False)

    with pytest.raises(RuntimeError, match="market price"):
        provider.get_latest_price("UNKNOWN")
    with pytest.raises(RuntimeError, match="news"):
        provider.get_recent_news("UNKNOWN")


def test_live_fundamental_provider_never_returns_mock_snapshot(monkeypatch):
    monkeypatch.setattr(httpx, "Client", _FailedHTTPClient)

    with pytest.raises(RuntimeError, match="fundamental"):
        MockFundamentalProvider(allow_mock=False).get_fundamentals("UNKNOWN")


def test_structured_stock_context_minimizes_account_data():
    position = _position()
    score = score_stock(position)
    recommendation = build_recommendation(position)
    context = build_structured_stock_context(
        position=position,
        score=score,
        recommendation=recommendation,
        technicals=None,
        fundamentals=None,
        valuation=None,
        catalysts=None,
        portfolio_timestamp=position.updated_at,
    )

    assert "account_id" not in context["position"]
    assert "quantity" not in context["position"]
    assert "avg_cost" not in context["position"]
    assert context["data_quality"]["missing_categories_count"] > 2


def test_portfolio_prompt_contains_no_trade_execution_payload():
    position = _position()
    summary = _summary()
    risk = analyze_portfolio_risk(summary, [position])
    prompt = build_portfolio_memo_prompt(
        summary=summary,
        positions=[position],
        risk=risk,
        recommendations=[build_recommendation(position)],
    ).lower()

    forbidden = [
        "proposed_trade_qty",
        "proposed_trade_value",
        '"action": "buy"',
        '"action": "sell"',
        '"account_id"',
        '"buying_power"',
        '"quantity"',
        '"avg_cost"',
    ]
    assert all(term not in prompt for term in forbidden)


def test_gemini_json_request_is_structured_only_and_not_falsely_grounded(monkeypatch):
    captured_payloads: list[dict] = []

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps({"summary": "ok"})}]}}
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            captured_payloads.append(kwargs["json"])
            return _Response()

    monkeypatch.setattr(httpx, "Client", _Client)
    client = GeminiClient(api_key="test-key-123", model="gemini-2.5-flash")

    assert client.generate_json('{"structured": true}', tools=[]) == {"summary": "ok"}
    assert "tools" not in captured_payloads[0]
    assert client.last_grounding_used is False
    assert client.generate_text('{"structured": true}', tools=[]) == '{"summary": "ok"}'
    assert "tools" not in captured_payloads[1]
    assert client.last_grounding_used is False


def test_ai_configuration_does_not_persist_api_key(monkeypatch):
    persisted: list[dict[str, str]] = []
    monkeypatch.setattr(
        "app.core.persistence.update_env_file",
        lambda values: persisted.append(values),
    )

    ai_routes.configure_ai(
        ai_routes.AIConfigureRequest(
            api_key="test-key-123456789",
            model="gemini-2.5-flash",
        )
    )

    assert all("GEMINI_API_KEY" not in values for values in persisted)


def test_fallback_analysis_contains_no_invented_market_facts_or_orders():
    text = ai_routes._get_fallback_analysis_text("morning", 100_000, 20_000).lower()

    assert "aapl" not in text
    assert "nvda" not in text
    assert "$185" not in text
    assert "limit" not in text
    assert "data unavailable" in text


def test_compliance_sanitizer_handles_nested_execution_language():
    report = {
        "summary": "Review only.",
        "claims": [{"text": "Order submitted; broker will buy 10 shares."}],
    }

    secured = append_compliance_disclaimer(report)
    serialized = json.dumps(secured).lower()

    assert "order submitted" not in serialized
    assert "broker will buy" not in serialized


def test_advanced_risk_does_not_fill_missing_history_with_plausible_defaults():
    metrics = calculate_advanced_risk_metrics([_position()], _summary(), [])

    assert metrics.max_drawdown is None
    assert metrics.volatility is None
    assert metrics.portfolio_beta_spy is None
    assert metrics.portfolio_beta_qqq is None
    assert metrics.value_at_risk_95 is None
    assert metrics.conditional_var_95 is None
    assert metrics.data_quality["historical_metrics"] == "insufficient"
    assert metrics.data_quality["cash_flow_ledger"] == "insufficient_history"
    assert metrics.data_quality["security_return_series"] in {
        "sufficient_modeled_current_holdings",
        "partial_modeled_current_holdings",
    }
    if metrics.correlation_matrix:
        assert all(
            metrics.correlation_matrix[symbol][symbol] == 1.0
            for symbol in metrics.correlation_matrix
        )


def test_attribution_does_not_invent_benchmark_return_or_alpha():
    snapshot = PortfolioPnLSnapshot(
        date=date.today().isoformat(),
        timestamp=utc_now().isoformat(),
        net_liquidation=100_000,
        cash=20_000,
        buying_power=40_000,
        margin_requirement=0,
        daily_pnl=0,
        daily_pnl_percent=0,
        positions=[],
    )
    attribution = calculate_performance_attribution([_position()], [snapshot])

    assert attribution.benchmark_relative_alpha is None
    assert attribution.data_quality["benchmark_data"] == "missing"


def test_thesis_tracker_weakens_when_required_evidence_is_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.thesis_tracker.get_thesis",
        lambda symbol: {
            "symbol": symbol,
            "thesis": "Growth and margins remain durable.",
            "key_assumptions": ["Revenue growth remains positive", "Margins remain resilient"],
            "break_triggers": ["Sustained growth slowdown", "Margin compression"],
            "updated_at": "2026-06-11T18:00:00Z",
        },
    )

    result = evaluate_thesis(
        _position(),
        score_stock(_position()),
        {
            "missing_categories_count": 2,
            "missing_categories": ["fundamentals", "catalysts"],
        },
        current_data={"fundamentals": None, "technicals": None, "catalysts": None},
    )

    assert result["status"] == "weakened"
    assert any(check["status"] == "not_evaluable" for check in result["assumption_checks"])


def test_thesis_tracker_marks_explicit_growth_trigger_broken(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.thesis_tracker.get_thesis",
        lambda symbol: {
            "symbol": symbol,
            "thesis": "Growth remains positive.",
            "key_assumptions": ["Revenue growth remains positive"],
            "break_triggers": ["Sustained growth slowdown"],
            "updated_at": "2026-06-11T18:00:00Z",
        },
    )

    result = evaluate_thesis(
        _position(),
        None,
        {"missing_categories_count": 0, "missing_categories": []},
        current_data={
            "fundamentals": {"revenue_growth_yoy": -0.05},
            "technicals": None,
            "catalysts": [],
        },
    )

    assert result["status"] == "broken"
    assert "Sustained growth slowdown" in result["triggered_break_conditions"]


def test_ibkr_sync_connector_replaces_running_event_loop(monkeypatch):
    class _RunningLoop:
        def is_closed(self):
            return False

        def is_running(self):
            return True

    replacement = asyncio.new_event_loop()
    installed = []
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: _RunningLoop())
    monkeypatch.setattr(asyncio, "new_event_loop", lambda: replacement)
    monkeypatch.setattr(asyncio, "set_event_loop", installed.append)

    try:
        assert _ensure_sync_event_loop() is replacement
        assert installed == [replacement]
    finally:
        replacement.close()


def test_live_fx_failure_never_uses_hardcoded_rate(monkeypatch):
    class _Response:
        status_code = 503

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(httpx, "Client", _Client)

    with pytest.raises(RuntimeError, match="Live FX rate unavailable"):
        get_exchange_rate("CHF", "JPY")


def test_scheduler_does_not_backfill_missed_analysis_slots(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "_load_settings",
        lambda: {
            "enabled": True,
            "morning_time": "09:30",
            "midday_time": "12:30",
            "night_time": "20:00",
        },
    )
    monkeypatch.setattr(scheduler, "_load_runs", lambda: [])
    monkeypatch.setattr(
        scheduler,
        "get_broker_adapter",
        lambda: pytest.fail("A missed schedule must not connect to IBKR"),
    )

    scheduler._run_scheduler_sync(datetime(2026, 6, 11, 18, 0))


def test_disconnected_snapshot_endpoint_never_records_dummy_portfolio():
    class _OfflineAdapter:
        def get_accounts(self):
            raise ConnectionError("IB Gateway unavailable")

    with pytest.raises(HTTPException) as exc:
        create_pnl_snapshot(adapter=_OfflineAdapter())

    assert exc.value.status_code == 503
