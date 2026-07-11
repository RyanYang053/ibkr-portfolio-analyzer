
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.domain import AccountSummary, Position, utc_now
from app.services.data_quality.validation import (
    build_valuation_disclosure,
    prepare_professional_response,
    require_analytics_safe,
    validate_portfolio_snapshot,
)


def _summary() -> AccountSummary:
    return AccountSummary(
        account_id="TEST-001",
        net_liquidation=11_100.0,
        cash=10_000.0,
        buying_power=0.0,
        margin_requirement=0.0,
        excess_liquidity=0.0,
        total_unrealized_pnl=0.0,
        total_realized_pnl=0.0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )


def _position(**overrides) -> Position:
    base = dict(
        account_id="TEST-001",
        symbol="MSFT",
        company_name="Microsoft",
        asset_class="STK",
        quantity=10.0,
        avg_cost=100.0,
        market_price=110.0,
        market_value=1100.0,
        unrealized_pnl=100.0,
        realized_pnl=0.0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=1.1,
        stock_type="core",
        is_etf=False,
        is_speculative=False,
        con_id=12345,
        updated_at=utc_now(),
    )
    base.update(overrides)
    return Position(**base)


def test_missing_market_price_blocks_professional_gate():
    summary = _summary()
    position = _position(market_price=0.0)
    validation = validate_portfolio_snapshot(summary, [position], fx_resolver=lambda _from, _to: 1.0)
    try:
        require_analytics_safe(validation)
        blocked = False
    except Exception:
        blocked = True
    assert blocked is True


def test_valuation_disclosure_reports_exclusions():
    summary = _summary()
    positions = [_position(), _position(symbol="BAD", con_id=999, market_price=0.0, market_value=0.0, quantity=5.0)]
    validation = validate_portfolio_snapshot(summary, positions, fx_resolver=lambda _from, _to: 1.0)
    disclosure = build_valuation_disclosure(summary, positions, validation)
    assert disclosure["excluded_con_ids"] == [999]
    assert "BAD" in disclosure["exclusion_reasons"]
    assert disclosure["included_gross_value_percent"] is None
    assert disclosure["coverage_measurable"] is False


def test_prepare_professional_response_includes_compliance_fields():
    summary = _summary()
    positions = [_position()]
    validation = validate_portfolio_snapshot(summary, positions, fx_resolver=lambda _from, _to: 1.0)
    payload = prepare_professional_response({"methodology": "test"}, summary, positions, validation)
    assert payload["snapshot_validation"]["status"] in {"pass", "warning"}
    assert payload["valuation_disclosure"]["validation_status"] in {"pass", "warning"}
    assert "robo_advisor_disclosure" in payload


def test_advanced_risk_route_blocks_invalid_snapshot(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.disable_auth_enforcement", True)
    monkeypatch.setattr("app.core.config.settings.broker_mode", "mock_ibkr_readonly")

    def _fail_validation(summary, positions, *, fx_resolver=None):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={"code": "PORTFOLIO_SNAPSHOT_INVALID", "issues": []},
        )

    monkeypatch.setattr("app.api.routes.portfolio.validate_and_gate_snapshot", _fail_validation)
    client = TestClient(app)
    response = client.get("/portfolio/advanced-risk?account_id=MOCK-001")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PORTFOLIO_SNAPSHOT_INVALID"


def test_advanced_risk_route_returns_validation_metadata(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.disable_auth_enforcement", True)
    monkeypatch.setattr("app.core.config.settings.broker_mode", "mock_ibkr_readonly")

    def _pass_validation(summary, positions, *, fx_resolver=None):
        return {
            "status": "pass",
            "score": 100,
            "issues": [],
            "metrics": {},
            "methodology": "test",
        }

    monkeypatch.setattr("app.api.routes.portfolio.validate_and_gate_snapshot", _pass_validation)
    client = TestClient(app)
    response = client.get("/portfolio/advanced-risk?account_id=MOCK-001")
    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_validation" in payload
    assert "valuation_disclosure" in payload
