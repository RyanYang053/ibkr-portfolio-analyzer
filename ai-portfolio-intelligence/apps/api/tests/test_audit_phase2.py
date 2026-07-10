from datetime import date, timedelta

import pytest

from app.schemas.domain import FundamentalSnapshot, Position, Transaction, utc_now
from app.services.attribution.engine import calculate_brinson_attribution, calculate_performance_attribution
from app.services.fundamentals.sector_models import get_sector_norms, resolve_scoring_model, score_fundamentals_for_sector
from app.services.portfolio.performance_returns import calculate_time_weighted_return, calculate_xirr
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.ledger_coverage import external_cash_flow_amount
from app.services.portfolio.transaction_store import save_transactions
from app.services.scoring.calibration import run_score_calibration


def _position(symbol: str, sector: str, market_value: float = 10000.0) -> Position:
    return Position(
        account_id="MOCK-001",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=10,
        avg_cost=100.0,
        market_price=100.0,
        market_value=market_value,
        unrealized_pnl=500.0,
        currency="USD",
        exchange="NASDAQ",
        sector=sector,
        industry="Software",
        portfolio_weight=10.0,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
        con_id=123456,
        local_symbol=symbol,
    )


def test_positions_include_con_id_identity():
    position = _position("MSFT", "Technology")
    assert position.con_id == 123456
    assert position.local_symbol == "MSFT"


def test_external_cash_flow_signs():
    assert external_cash_flow_amount(
        Transaction(
            account_id="A",
            symbol="CASH",
            trade_date=date.today(),
            action="deposit",
            quantity=1,
            price=1000,
            commission=0,
            currency="USD",
            amount=1000,
        )
    ) == 1000
    assert external_cash_flow_amount(
        Transaction(
            account_id="A",
            symbol="CASH",
            trade_date=date.today(),
            action="withdrawal",
            quantity=1,
            price=500,
            commission=0,
            currency="USD",
            amount=500,
        )
    ) == -500


def test_time_weighted_return_compounds_daily_returns():
    twr = calculate_time_weighted_return([0.01, -0.005, 0.02])
    assert twr is not None
    assert round(twr * 100, 2) == 2.5


def test_xirr_solves_simple_two_point_flow():
    flows = [
        (date(2025, 1, 1), -1000.0),
        (date(2026, 1, 1), 1100.0),
    ]
    xirr = calculate_xirr(flows)
    assert xirr is not None
    assert 0.09 < xirr < 0.11


def test_sector_specific_valuation_uses_sector_norms():
    fundamentals = FundamentalSnapshot(
        symbol="MSFT",
        period="TTM",
        report_date=date.today(),
        revenue_growth_yoy=0.18,
        gross_margin=0.68,
        operating_margin=0.42,
        free_cash_flow=10_000_000_000,
        cash=80_000_000_000,
        total_debt=30_000_000_000,
        pe_forward=28,
        ev_sales=9.0,
        fcf_yield=0.03,
    )
    scores = score_fundamentals_for_sector(fundamentals, "Technology")
    assert "valuation" in scores
    assert get_sector_norms("Financials").model_name == "financials_pb_rotce"


def test_scoring_model_routes_by_sector():
    position = _position("JPM", "Financials")
    assert resolve_scoring_model(position) == "financials_pb_rotce"


def test_brinson_attribution_withheld_without_portfolio_sector_returns():
    positions = [
        _position("MSFT", "Technology", 30000),
        _position("JPM", "Financials", 10000),
    ]
    alloc, sel, inter, active, by_sector, methodology = calculate_brinson_attribution(
        positions,
        "USD",
        lambda _from, _to: 1.0,
        allow_mock=True,
    )
    assert by_sector == {}
    assert alloc is None
    assert sel is None
    assert inter is None
    assert active is None
    assert "withheld" in methodology.lower()


def test_performance_attribution_includes_brinson_fields():
    positions = [_position("MSFT", "Technology")]
    history = [
        PortfolioPnLSnapshot(
            date=date.today().isoformat(),
            timestamp=utc_now().isoformat(),
            net_liquidation=100000,
            cash=10000,
            buying_power=50000,
            margin_requirement=5000,
            daily_pnl=100,
            daily_pnl_percent=0.1,
            positions=[],
            external_cash_flow=0.0,
        )
    ]
    result = calculate_performance_attribution(positions, history, base_currency="USD", fx_resolver=lambda _a, _b: 1.0)
    assert result.brinson_by_sector == {}
    assert result.data_quality["brinson_attribution"] == "insufficient"


def test_score_calibration_reports_ic_and_buckets():
    observations = [
        {"score": 80, "forward_return": 0.10},
        {"score": 75, "forward_return": 0.08},
        {"score": 60, "forward_return": 0.02},
        {"score": 40, "forward_return": -0.03},
    ]
    report = run_score_calibration(observations, model_name="technology_growth")
    assert report.observation_count == 4
    assert report.information_coefficient is not None
    assert report.calibration_buckets


def test_transaction_store_deduplicates(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.portfolio.transaction_store.DATA_DIR", str(tmp_path))
    txn = Transaction(
        account_id="MOCK-001",
        symbol="MSFT",
        trade_date=date.today(),
        action="buy",
        quantity=1,
        price=100,
        commission=1,
        currency="USD",
        transaction_id="abc123",
    )
    save_transactions("MOCK-001", [txn, txn])
    from app.services.portfolio.transaction_store import load_transactions

    assert len(load_transactions("MOCK-001")) == 1
