from fastapi.testclient import TestClient

from app.main import app
from app.schemas.domain import Position, utc_now
from app.services.scoring.stock_score import score_stock


def test_stock_data_provider_endpoints_do_not_return_mock_data_by_default():
    client = TestClient(app)

    for path in [
        "/stocks/MSFT/fundamentals",
        "/stocks/MSFT/technicals",
        "/stocks/MSFT/valuation",
        "/stocks/MSFT/news",
    ]:
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "DATA_PROVIDER_NOT_CONFIGURED"


def test_score_stock_withholds_score_in_live_mode_without_data():
    position = Position(
        account_id="U1234567",
        symbol="INVALIDTICKER",
        company_name="Invalid Ticker Inc",
        asset_class="STK",
        quantity=100,
        avg_cost=150.0,
        market_price=160.0,
        market_value=16000.0,
        unrealized_pnl=1000.0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=5.0,
        stock_type="core",
        updated_at=utc_now(),
    )
    # Call with allow_mock=False to simulate live mode failure
    score = score_stock(position, allow_mock=False)
    assert score.final_score is None
    assert score.interpretation == "Data Not Found"
    assert "portfolio_fit" in score.sub_scores
    assert len(score.sub_scores) == 1
    assert "fundamental" in score.explanation.lower() or "technical" in score.explanation.lower()


def test_stock_endpoint_raises_404_for_invalid_symbol_in_live_mode():
    client = TestClient(app)
    # Default broker mode is "ibkr_readonly" (live/real mode)
    response = client.get("/stocks/INVALIDTICKER")
    assert response.status_code == 404

