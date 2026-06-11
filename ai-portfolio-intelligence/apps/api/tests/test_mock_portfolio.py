from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.scoring.stock_score import score_stock
from app.services.risk.portfolio_risk import analyze_portfolio_risk


def test_mock_ibkr_portfolio_contains_required_sample_symbols_and_classifications():
    adapter = MockIBKRAdapter()

    positions = adapter.get_positions("MOCK-001")
    by_symbol = {position.symbol: position for position in positions}

    assert {"QQQ", "SPY", "MSFT", "META", "GOOGL", "SOXX", "SOFI", "CRM", "CELH", "NKE", "IONQ", "LAES", "INFQ"}.issubset(by_symbol)
    assert by_symbol["QQQ"].is_etf is True
    assert by_symbol["SPY"].stock_type == "etf"
    assert by_symbol["MSFT"].stock_type == "mega_cap_quality"
    assert by_symbol["IONQ"].is_speculative is True
    assert by_symbol["LAES"].stock_type == "speculative_growth"


def test_portfolio_risk_flags_concentration_and_speculative_exposure():
    adapter = MockIBKRAdapter()
    summary = adapter.get_account_summary("MOCK-001")
    positions = adapter.get_positions("MOCK-001")

    risk = analyze_portfolio_risk(summary, positions)

    assert 0 <= risk.risk_score <= 100
    assert risk.herfindahl_concentration_score > 0
    assert risk.herfindahl_concentration_label in {"Diversified", "Moderate concentration", "High concentration", "Very concentrated"}
    assert risk.total_value == summary.net_liquidation
    assert "Technology" in risk.sector_exposure
    assert any(alert.alert_type == "sector_concentration" for alert in risk.alerts)
    assert any(alert.alert_type == "speculative_exposure" for alert in risk.alerts)


def test_stock_scoring_uses_stock_type_specific_model():
    adapter = MockIBKRAdapter()
    positions = {position.symbol: position for position in adapter.get_positions("MOCK-001")}

    etf_score = score_stock(positions["QQQ"])
    speculative_score = score_stock(positions["IONQ"])

    assert etf_score.stock_type == "etf"
    assert "market_trend" in etf_score.sub_scores
    assert speculative_score.stock_type == "speculative_growth"
    assert "cash_runway" in speculative_score.sub_scores
    assert 0 <= etf_score.final_score <= 100
    assert 0 <= speculative_score.final_score <= 100
