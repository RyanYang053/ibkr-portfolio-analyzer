from datetime import date

from app.schemas.domain import Position, Transaction, utc_now
from app.services.fundamentals.sector_models import get_sector_norms, resolve_scoring_model
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.scoring.decision_engine import build_recommendation


def _position(symbol: str = "MSFT", score_weight: float = 5.0) -> Position:
    return Position(
        account_id="MOCK-001",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=100,
        avg_cost=100.0,
        market_price=200.0,
        market_value=20000.0,
        unrealized_pnl=10000.0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=score_weight,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )


def test_strong_add_disabled_without_calibration(monkeypatch):
    monkeypatch.setattr("app.services.scoring.decision_engine.settings.enable_strong_add_recommendations", False)
    monkeypatch.setattr(
        "app.services.scoring.decision_engine.score_stock",
        lambda _position, allow_mock=True: type(
            "Score",
            (),
            {
                "final_score": 90.0,
                "confidence": "High",
                "explanation": "High coverage.",
                "missing_data": [],
                "supporting_evidence": [],
                "data_timestamp": utc_now(),
            },
        )(),
    )
    recommendation = build_recommendation(_position())
    assert recommendation.action == "Add"
    assert recommendation.action != "Strong Add"


def test_sector_models_use_heuristic_names_not_unavailable_inputs():
    assert get_sector_norms("Financials").model_name == "financials_heuristic"
    assert get_sector_norms("Real Estate").model_name == "reit_heuristic"
    financials_position = _position("JPM")
    financials_position.sector = "Financials"
    assert resolve_scoring_model(financials_position) == "financials_heuristic"


def test_strong_add_requires_calibration_when_enabled(monkeypatch):
    monkeypatch.setattr("app.services.scoring.decision_engine.settings.enable_strong_add_recommendations", True)
    monkeypatch.setattr("app.services.scoring.decision_engine.get_calibration_status", lambda _model: "insufficient")
    monkeypatch.setattr(
        "app.services.scoring.decision_engine.score_stock",
        lambda _position, allow_mock=True: type(
            "Score",
            (),
            {
                "final_score": 90.0,
                "confidence": "High",
                "explanation": "High coverage.",
                "missing_data": [],
                "supporting_evidence": [],
                "data_timestamp": utc_now(),
            },
        )(),
    )
    recommendation = build_recommendation(_position())
    assert recommendation.action == "Add"


def test_same_currency_tax_lot_fifo_realized_gain():
    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=10,
            price=100,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2025, 6, 1),
            action="sell",
            quantity=4,
            price=130,
            commission=0,
            currency="USD",
        ),
    ]
    report = build_tax_lot_attribution("MOCK-001", transactions, reporting_currency="USD")
    assert report.data_quality["status"] == "sufficient"
    assert report.total_realized_gain_loss == 120.0

    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=100,
            price=100,
            commission=0,
            currency="CAD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2025, 1, 1),
            action="sell",
            quantity=50,
            price=120,
            commission=0,
            currency="CAD",
        ),
    ]
    report = build_tax_lot_attribution("MOCK-001", transactions, reporting_currency="USD")
    assert report.data_quality["status"] == "incomplete"
    assert report.data_quality["fx_conversion"] == "withheld_mixed_currency"
    assert report.total_realized_gain_loss == 0.0
