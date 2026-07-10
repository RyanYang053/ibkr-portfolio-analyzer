from fastapi.testclient import TestClient

from app.api.deps import get_broker_adapter
from app.main import app
from app.schemas.domain import InvestorProfile, Position, utc_now
from app.services.ai.client import GeminiClient, configure_runtime_gemini, resolve_gemini_credentials
from app.services.ai.report_generator import generate_daily_portfolio_memo
from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.provenance import build_report_provenance, collect_position_source_records
from app.services.suitability.engine import save_investor_profile


def test_daily_report_uses_authenticated_user_policy(monkeypatch):
    adapter = MockIBKRAdapter()
    app.dependency_overrides[get_broker_adapter] = lambda: adapter
    client = TestClient(app)

    save_investor_profile(
        InvestorProfile(
            objective="Capital Preservation",
            time_horizon_years=5,
            risk_tolerance="Low",
            risk_capacity="Low",
            liquidity_needs=5000.0,
            net_worth_range="100k-500k",
            tax_residency="Canada",
            account_type="Tax-Free",
            restrictions=[],
        ),
        "MOCK-001",
        user_id="local-dev",
    )

    response = client.post("/reports/daily?account_id=MOCK-001")
    assert response.status_code == 200
    payload = response.json()
    assert "Capital Preservation" in payload["report_json"]["suitability_and_compliance"]
    app.dependency_overrides.clear()


def test_different_users_get_different_suitability_results():
    adapter = MockIBKRAdapter()
    summary = adapter.get_account_summary("MOCK-001")
    positions = adapter.get_positions("MOCK-001")

    save_investor_profile(
        InvestorProfile(
            objective="Growth",
            time_horizon_years=10,
            risk_tolerance="High",
            risk_capacity="High",
            liquidity_needs=10000.0,
            net_worth_range="500k-1m",
            tax_residency="Canada",
            account_type="Tax-Free",
            restrictions=[],
        ),
        "MOCK-001",
        user_id="user-a",
    )
    save_investor_profile(
        InvestorProfile(
            objective="Capital Preservation",
            time_horizon_years=3,
            risk_tolerance="Low",
            risk_capacity="Low",
            liquidity_needs=5000.0,
            net_worth_range="100k-500k",
            tax_residency="Canada",
            account_type="Tax-Free",
            restrictions=[],
        ),
        "MOCK-001",
        user_id="user-b",
    )

    report_a = generate_daily_portfolio_memo(summary, positions, user_id="user-a")
    report_b = generate_daily_portfolio_memo(summary, positions, user_id="user-b")

    assert report_a.report_json["suitability_and_compliance"] != report_b.report_json["suitability_and_compliance"]


def test_production_runtime_gemini_configuration_is_rejected(monkeypatch):
    monkeypatch.setattr("app.api.routes.ai.settings.environment", "production")
    client = TestClient(app)

    response = client.post(
        "/ai/configure",
        json={"api_key": "test-secret-key", "model": "gemini-2.5-flash"},
    )

    assert response.status_code == 403
    assert "disabled in production" in response.json()["detail"]


def test_api_and_scheduler_resolve_same_configured_model(monkeypatch):
    monkeypatch.setattr("app.services.ai.client.settings.environment", "production")
    monkeypatch.setattr("app.services.ai.client.settings.gemini_api_key", "env-key")
    monkeypatch.setattr("app.services.ai.client.settings.gemini_model", "gemini-2.5-pro")
    monkeypatch.setattr("app.services.ai.client._runtime_api_key", "runtime-only-key")
    monkeypatch.setattr("app.services.ai.client._runtime_model", "runtime-only-model")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    api_client = GeminiClient()
    scheduler_client = GeminiClient()

    assert api_client.api_key == scheduler_client.api_key == "env-key"
    assert api_client.model == scheduler_client.model == "gemini-2.5-pro"


def test_runtime_configure_ignored_in_production(monkeypatch):
    monkeypatch.setattr("app.services.ai.client.settings.environment", "production")
    try:
        configure_runtime_gemini("should-not-stick", "runtime-model")
    except RuntimeError:
        pass
    key, _model = resolve_gemini_credentials()
    assert key != "should-not-stick"


def test_provenance_reflects_exact_position_sources():
    positions = [
        Position(
            account_id="MOCK-001",
            symbol="MSFT",
            company_name="Microsoft",
            asset_class="STK",
            quantity=10,
            avg_cost=100,
            market_price=110,
            market_value=1100,
            unrealized_pnl=100,
            realized_pnl=0,
            currency="USD",
            exchange="NASDAQ",
            sector="Technology",
            industry="Software",
            portfolio_weight=10,
            stock_type="large_cap",
            is_etf=False,
            is_speculative=False,
            updated_at=utc_now(),
            price_source="broker_snapshot",
        )
    ]

    records = collect_position_source_records(positions)
    assert len(records) == 1
    assert records[0].provider == "broker_snapshot"
    assert records[0].observation_id == "MSFT"

    provenance = build_report_provenance(positions)
    assert provenance.live_portfolio_data is True
    assert provenance.mock_fallback_data is False
