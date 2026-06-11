from app.services.ai.report_generator import generate_daily_portfolio_memo
from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.scoring.decision_engine import build_recommendation
from app.services.technicals.indicators import calculate_technical_indicators


def test_technical_indicators_calculate_trend_and_momentum():
    prices = [100 + index for index in range(220)]

    indicators = calculate_technical_indicators("MSFT", prices)

    assert indicators.symbol == "MSFT"
    assert indicators.sma_20 > indicators.sma_50 > indicators.sma_200
    assert indicators.rsi_14 > 50
    assert indicators.trend_classification in {"strong uptrend", "uptrend"}


def test_decision_support_uses_non_execution_language_and_human_review():
    adapter = MockIBKRAdapter()
    position = next(position for position in adapter.get_positions("MOCK-001") if position.symbol == "MSFT")

    recommendation = build_recommendation(position)

    assert recommendation.human_review_required is True
    assert recommendation.action in {"Strong Add", "Add", "Hold", "Watch", "Trim Review", "Exit Review", "Avoid", "Data Insufficient"}
    if recommendation.action == "Data Insufficient":
        assert recommendation.add_zone is None
    assert "execute" not in recommendation.explanation.lower()
    assert "order" not in recommendation.explanation.lower()
    assert "Human review required" in recommendation.human_review_reminder


def test_daily_report_includes_required_no_trading_disclaimer():
    adapter = MockIBKRAdapter()

    report = generate_daily_portfolio_memo(
        adapter.get_account_summary("MOCK-001"),
        adapter.get_positions("MOCK-001"),
    )

    assert report.human_review_required is True
    assert "does not execute trades" in report.disclaimer
    assert "decision support" in report.disclaimer
    assert report.risk_alerts
