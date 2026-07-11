from fastapi.testclient import TestClient

from app.api.deps import get_broker_adapter
from app.main import app
from app.schemas.domain import Position, utc_now
from app.services.ai.client import GeminiAPIError, GeminiClient
from app.services.ai.prompt_templates import build_stock_analysis_prompt
from app.services.ai.report_generator import generate_stock_research_report
from app.services.ai.structured_outputs import build_structured_stock_context, evaluate_confidence_limits
from app.services.broker.mock_ibkr import MockIBKRAdapter


def test_stock_prompt_enforces_evidence_and_no_trading_language():
    adapter = MockIBKRAdapter()
    position = next(position for position in adapter.get_positions("MOCK-001") if position.symbol == "MSFT")

    prompt = build_stock_analysis_prompt(position=position, score=None, recommendation=None)

    assert "using only the provided structured data" in prompt
    assert "Do not create or submit orders" in prompt
    assert "does not execute trades" in prompt
    assert "Return strict JSON" in prompt
    assert "evidence_ids" in prompt
    assert "data_quality" in prompt
    assert "thesis_status" in prompt
    assert "broker_credentials" in prompt
    assert "account_passwords" in prompt


def test_stock_report_falls_back_without_gemini_key_and_keeps_disclaimer(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.ai.client.settings.gemini_api_key", None)
    monkeypatch.setattr("app.services.ai.client._runtime_api_key", None)
    adapter = MockIBKRAdapter()
    position = next(position for position in adapter.get_positions("MOCK-001") if position.symbol == "MSFT")

    report = generate_stock_research_report(position)

    assert report["symbol"] == "MSFT"
    assert report["provider"] == "deterministic_fallback"
    assert report["human_review_required"] is True
    assert "does not execute trades" in report["disclaimer"]
    assert "order" not in report["action"].lower()
    assert report["schema_version"] == "stock_ai_analysis.v1"
    assert report["thesis"]["status"] in {"intact", "weakened", "broken"}
    assert report["thesis_invalidation_triggers"]
    assert report["evidence"]
    assert report["claims"]
    assert all(claim["evidence_ids"] for claim in report["claims"])
    evidence_ids = {item["id"] for item in report["evidence"]}
    for claim in report["claims"]:
        assert set(claim["evidence_ids"]).issubset(evidence_ids)


def test_manual_ai_stock_analysis_endpoint_returns_decision_support_report():
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)

    response = client.post("/ai/analyze-stock/MSFT?account_id=MOCK-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "MSFT"
    assert payload["human_review_required"] is True
    assert "does not execute trades" in payload["disclaimer"]
    assert "provider" in payload
    assert payload["schema_version"] == "stock_ai_analysis.v1"
    assert payload["data_quality"]["confidence_cap"] in {"High", "Medium-High", "Medium", "Low"}
    assert payload["claims"][0]["evidence_ids"]
    app.dependency_overrides.clear()


def test_ai_configure_endpoint_sets_key_without_echoing_secret():
    client = TestClient(app)

    response = client.post(
        "/ai/configure",
        json={"api_key": "test-secret-key", "model": "gemini-3.5-flash"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert "api_key" not in payload
    assert "test-secret-key" not in response.text


def test_gemini_client_surfaces_google_error_body(monkeypatch):
    class FakeResponse:
        status_code = 400
        text = '{"error":{"code":400,"message":"API key not valid","status":"INVALID_ARGUMENT"}}'

        def raise_for_status(self):
            import httpx

            raise httpx.HTTPStatusError("bad request", request=None, response=self)

        def json(self):
            return {"error": {"code": 400, "message": "API key not valid", "status": "INVALID_ARGUMENT"}}

    class FakeHTTPClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr("app.services.ai.client.httpx.Client", FakeHTTPClient)

    try:
        GeminiClient(api_key="test-key", model="gemini-3.5-flash").generate_json("return {}")
    except GeminiAPIError as exc:
        assert "Gemini API 400 INVALID_ARGUMENT: API key not valid" in str(exc)
    else:
        raise AssertionError("Expected GeminiAPIError")


def test_data_quality_rules_limit_confidence_and_action_when_inputs_missing():
    context = build_structured_stock_context(
        position=None,
        score=None,
        recommendation=None,
        technicals=None,
        fundamentals=None,
        valuation=None,
        catalysts=None,
        portfolio_timestamp=None,
    )

    limits = evaluate_confidence_limits(context)

    assert limits["confidence_cap"] == "Low"
    assert limits["action_override"] == "Data Insufficient"
    assert limits["add_zone_allowed"] is False
    assert context["scores"]["technical_score"] is None
    assert context["scores"]["catalyst_score"] is None
    assert context["thesis"]["status"] == "weakened"
    assert context["data_quality"]["missing_categories_count"] > 2


def test_missing_price_removes_add_zone_but_keeps_evidence_traceability():
    adapter = MockIBKRAdapter()
    position = next(position for position in adapter.get_positions("MOCK-001") if position.symbol == "MSFT")
    payload = build_structured_stock_context(
        position=position.model_copy(update={"market_price": 0}),
        score=None,
        recommendation=None,
        technicals=None,
        fundamentals=None,
        valuation=None,
        catalysts=[],
        portfolio_timestamp=utc_now(),
    )

    report = generate_stock_research_report(position.model_copy(update={"market_price": 0}))

    assert payload["data_quality"]["categories"]["price"]["missing"] is True
    assert report["add_zone"] is None
    assert all(claim["evidence_ids"] for claim in report["claims"])


def test_live_symbol_without_mock_history_marks_technicals_missing_instead_of_crashing():
    position = Position(
        account_id="LIVE-001",
        symbol="AMZN",
        company_name="AMZN",
        asset_class="STK",
        quantity=100,
        avg_cost=239.31,
        market_price=243.5,
        market_value=24350,
        unrealized_pnl=419,
        realized_pnl=0,
        currency="USD",
        exchange="NASDAQ",
        sector="Unknown",
        industry="Unknown",
        portfolio_weight=3.53,
        stock_type="unknown",
        is_etf=False,
        is_speculative=False,
        updated_at=utc_now(),
    )

    report = generate_stock_research_report(position)

    assert report["symbol"] == "AMZN"
    assert report["schema_version"] == "stock_ai_analysis.v1"
    assert "technicals" in report["data_quality"]["missing_categories"]
    assert report["scores"]["technical_score"] is None
    assert all(claim["evidence_ids"] for claim in report["claims"])


def test_thesis_tracker_endpoint_reads_and_updates_holding_thesis():
    client = TestClient(app)

    read_response = client.get("/ai/thesis/MSFT")
    assert read_response.status_code == 200
    assert read_response.json()["symbol"] == "MSFT"

    update_response = client.put(
        "/ai/thesis/MSFT",
        json={
            "thesis": "Microsoft thesis depends on cloud growth and AI monetization.",
            "key_assumptions": ["Cloud demand remains durable", "Margins remain resilient"],
            "break_triggers": ["Cloud growth decelerates materially", "Margin pressure persists"],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["symbol"] == "MSFT"
    assert "cloud growth" in payload["thesis"]
