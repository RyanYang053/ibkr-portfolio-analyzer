
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_broker_adapter
from app.core.config import settings
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.options.engine import (
    calculate_bull_call_spread_metrics,
    calculate_cash_secured_put_metrics,
    evaluate_strategy_eligibility,
)


def validate_schema(instance, schema):
    """Simple validator to check OPTIONS_STRATEGY_RESPONSE_SCHEMA constraints without external jsonschema dependency."""
    if schema.get("type") == "object":
        assert isinstance(instance, dict)
        for req in schema.get("required", []):
            assert req in instance, f"Missing required property: {req}"
        for k, v in instance.items():
            if k in schema.get("properties", {}):
                validate_schema(v, schema["properties"][k])
    elif schema.get("type") == "array":
        assert isinstance(instance, list)
        items_schema = schema.get("items", {})
        for item in instance:
            validate_schema(item, items_schema)
    elif schema.get("type") == "string":
        assert isinstance(instance, str)
    elif schema.get("type") == "boolean":
        assert isinstance(instance, bool)

def test_cash_secured_put_payoff_math():
    strike = 150.0
    premium = 3.50
    metrics = calculate_cash_secured_put_metrics(strike, premium)
    
    assert metrics["breakeven"] == 146.50
    assert metrics["required_cash"] == 15000.0
    assert "350.00" in metrics["max_profit"]
    assert "14650.00" in metrics["max_loss"]

def test_covered_call_requires_100_shares():
    # Less than 100 shares
    eligible, reason = evaluate_strategy_eligibility(
        strategy_name="Covered Call",
        strike=150.0,
        underlying_price=145.0,
        quantity_held=50,
        cash_available=1000.0
    )
    assert eligible is False
    assert "requires at least 100 shares" in reason

    # 100 shares
    eligible, reason = evaluate_strategy_eligibility(
        strategy_name="Covered Call",
        strike=150.0,
        underlying_price=145.0,
        quantity_held=100,
        cash_available=1000.0
    )
    assert eligible is True
    assert "holding at least 100 shares" in reason

def test_bull_call_spread_max_loss_math():
    long_strike = 145.0
    short_strike = 150.0
    net_debit = 1.50
    metrics = calculate_bull_call_spread_metrics(long_strike, short_strike, net_debit)
    
    assert metrics["breakeven"] == 146.50
    assert "350.00" in metrics["max_profit"]  # (5.00 - 1.50) * 100 = 350
    assert "150.00" in metrics["max_loss"]    # 1.50 * 100 = 150

def test_strategy_eligibility_other_rules():
    # Naked short call
    eligible, reason = evaluate_strategy_eligibility(
        strategy_name="Naked Short Call",
        strike=150.0,
        underlying_price=145.0,
        quantity_held=0,
        cash_available=10000.0
    )
    assert eligible is False
    assert "prohibited by risk policy" in reason.lower()

    # Cash secured put insufficient cash
    eligible, reason = evaluate_strategy_eligibility(
        strategy_name="Cash-Secured Put",
        strike=150.0,
        underlying_price=145.0,
        quantity_held=0,
        cash_available=5000.0
    )
    assert eligible is False
    assert "Requires $15,000.00 in cash" in reason

    # Spreads on non-margin account
    eligible, reason = evaluate_strategy_eligibility(
        strategy_name="Bull Call Spread",
        strike=150.0,
        underlying_price=145.0,
        quantity_held=0,
        cash_available=10000.0,
        account_type="Cash"
    )
    assert eligible is False
    assert "requires options multi-leg/margin approval" in reason

def test_options_strategy_route_success(monkeypatch):
    monkeypatch.setattr(settings, "allow_mock_options_strategy", True)
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)
    
    response = client.get("/stocks/MSFT/options-strategy?account_id=MOCK-001")
    assert response.status_code == 200
    
    payload = response.json()
    assert payload["symbol"] == "MSFT"
    assert "strategies" in payload
    assert len(payload["strategies"]) > 0
    assert payload["isMock"] is True
    assert "asOf" in payload
    assert "dataSource" in payload
    assert "warnings" in payload
    
    # Test specific properties on strategies
    strategy = payload["strategies"][0]
    assert "name" in strategy
    assert "expiration" in strategy
    assert "strikes" in strategy
    assert "max_profit" in strategy
    assert "max_loss" in strategy
    assert "breakeven" in strategy
    assert "eligible" in strategy
    assert "eligibility_reason" in strategy

    app.dependency_overrides.clear()

def test_options_strategy_mock_mode_flagged(monkeypatch):
    monkeypatch.setattr(settings, "allow_mock_options_strategy", True)
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)
    
    response = client.get("/stocks/MSFT/options-strategy?account_id=MOCK-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["isMock"] is True
    assert "Simulated data" in "".join(payload["warnings"])
    
    app.dependency_overrides.clear()

def test_options_strategy_no_order_language(monkeypatch):
    monkeypatch.setattr(settings, "allow_mock_options_strategy", True)
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)
    
    response = client.get("/stocks/MSFT/options-strategy?account_id=MOCK-001")
    assert response.status_code == 200
    payload = response.json()
    
    # Compliance checks: Avoid order placement words in strategy framing
    disclaimer = payload["disclaimer"].lower()
    assert "submit order" not in disclaimer
    assert "place order" not in disclaimer
    
    # Ensure strategies list avoids recommendation framing
    for strat in payload["strategies"]:
        name = strat["name"].lower()
        assert "recommended" not in name
        assert "best" not in name
        assert "buy" not in name
        assert "sell" not in name

    app.dependency_overrides.clear()

def test_options_data_unavailable_returns_safe_error(monkeypatch):
    # Disable mock fallback and Gemini Client mock settings, representing a production environment
    monkeypatch.setattr(settings, "allow_mock_options_strategy", False)
    monkeypatch.setattr(settings, "broker_mode", "ibkr_live")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.ai.client.settings.gemini_api_key", None)
    monkeypatch.setattr("app.services.ai.client._runtime_api_key", None)
    
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)
    
    response = client.get("/stocks/MSFT/options-strategy?account_id=MOCK-001")
    # Should raise 503 because live quotes and Gemini are unavailable in production mode
    assert response.status_code == 503
    detail = response.json()["detail"]
    if isinstance(detail, dict):
        message = detail.get("message", "")
    else:
        message = str(detail)
    assert (
        "Options strategy generation is unavailable" in message
        or "Live options quotes are unavailable" in message
    )
    
    app.dependency_overrides.clear()

def test_ai_schema_validation_against_prompt_schema():
    # Test validator rules on responses
    from app.services.ai.prompt_templates import OPTIONS_STRATEGY_RESPONSE_SCHEMA

    valid_response = {
        "symbol": "AAPL",
        "strategies": [
            {
                "name": "Covered Call",
                "type": "income",
                "expiration": "2026-07-16",
                "selected_strikes": "Sell 150 Call",
                "target_contract_symbols": ["AAPL260716C00150000"],
                "rationale": "Generate premium with low volatility."
            }
        ],
        "market_sentiment": "Moderate volatility.",
        "human_review_required": True,
        "disclaimer": "Educational candidate only."
    }
    
    # This should validate successfully without raising exceptions
    validate_schema(valid_response, OPTIONS_STRATEGY_RESPONSE_SCHEMA)

    # Missing expiration should fail validation
    invalid_response = {
        "symbol": "AAPL",
        "strategies": [
            {
                "name": "Covered Call",
                "type": "income",
                "selected_strikes": "Sell 150 Call",
                "target_contract_symbols": ["AAPL260716C00150000"],
                "rationale": "Generate premium."
            }
        ],
        "market_sentiment": "Moderate volatility.",
        "human_review_required": True,
        "disclaimer": "Educational candidate only."
    }

    with pytest.raises(AssertionError) as exc_info:
        validate_schema(invalid_response, OPTIONS_STRATEGY_RESPONSE_SCHEMA)
    assert "expiration" in str(exc_info.value)
