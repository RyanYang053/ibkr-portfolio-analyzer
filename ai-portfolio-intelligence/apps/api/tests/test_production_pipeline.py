from datetime import date, timedelta

import pytest

from app.schemas.domain import Position, Transaction, utc_now
from app.services.attribution.brinson_ledger import (
    beginning_sector_weights,
    reconstruct_holdings_at_date,
    sector_returns_from_ledger,
)
from app.services.portfolio.corporate_actions import parse_corporate_action
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.portfolio_construction.optimizer import generate_portfolio_optimization
from app.services.risk.factor_model import compute_measured_factor_exposures
from app.services.scoring.calibration_ingestion import (
    materialize_calibration_observations,
    record_score_observation,
)


def test_transaction_fx_resolver_enables_mixed_currency_tax_lots(monkeypatch):
    monkeypatch.setattr(
        "app.services.market_data.fx_store.get_historical_exchange_rate",
        lambda _from, _to, _as_of: 0.75,
    )
    from app.services.market_data.fx_store import make_transaction_fx_resolver

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
    report = build_tax_lot_attribution(
        "MOCK-001",
        transactions,
        reporting_currency="USD",
        fx_resolver=make_transaction_fx_resolver(),
    )
    assert report.data_quality["status"] == "lot_matching_complete"
    assert report.data_quality["fx_conversion"] == "transaction_date_fx"
    assert report.total_realized_gain_loss == 750.0


def test_stock_split_corporate_action_doubles_lot_quantity():
    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="SPY",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=10,
            price=400,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="SPY",
            trade_date=date(2024, 6, 1),
            action="corporate_action",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            description="Stock Split 2 for 1",
        ),
    ]
    action = parse_corporate_action(transactions[-1])
    assert action is not None
    assert action.action_type == "split"
    assert action.ratio == 2.0

    holdings = reconstruct_holdings_at_date(transactions, date(2024, 12, 31))
    assert holdings[("SPY", None)] == pytest.approx(20.0)


def test_calibration_ingestion_materializes_forward_return(monkeypatch, tmp_path):
    captured: list[dict] = []

    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion.PENDING_FILE",
        tmp_path / "pending.json",
    )
    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion._period_total_return",
        lambda symbol, _start, _end, allow_mock=False: 0.08 if symbol != "SPY" else 0.03,
    )
    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion.save_calibration_observations",
        lambda _model, observations: captured.extend(observations),
    )
    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion.load_calibration_observations",
        lambda _model, include_synthetic_demo=False: [],
    )

    observed = date.today() - timedelta(days=120)
    record_score_observation(
        symbol="MSFT",
        model_name="universal",
        score=82.0,
        observed_on=observed,
        model_version="2026.07.1",
        feature_snapshot_hash="abc123",
        input_sources=["live_yahoo_finance", "verified_close_only"],
        synthetic_demo=False,
    )
    promoted = materialize_calibration_observations("universal", allow_mock=True)
    assert promoted == 1
    assert captured[0]["forward_total_return"] == 0.08
    assert captured[0]["benchmark_total_return"] == 0.03
    assert captured[0]["forward_excess_return"] == pytest.approx(0.05)
    assert captured[0]["model_version"] == "2026.07.1"
    assert captured[0]["feature_snapshot_hash"] == "abc123"


def test_measured_factor_model_returns_exposures():
    from datetime import date, timedelta

    end = date.today()
    portfolio_returns = {
        (end - timedelta(days=index)).isoformat(): value
        for index, value in enumerate(reversed([0.01, -0.005, 0.008, 0.004, -0.002] * 6))
    }
    exposures, quality, metadata = compute_measured_factor_exposures(
        portfolio_returns,
        end_date=end,
        allow_mock=True,
    )
    assert quality in {"experimental", "insufficient_factor_history", "regression_failed", "insufficient_history"}
    if quality == "experimental":
        assert exposures
        assert metadata.get("observation_count", 0) >= 20


def test_portfolio_optimizer_produces_trade_proposal(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.optimization_liquidity_cap", 0.5)
    positions = [
        Position(
            account_id="MOCK-001",
            symbol="MSFT",
            company_name="Microsoft",
            asset_class="STK",
            quantity=50,
            avg_cost=300,
            market_price=400,
            market_value=20000,
            unrealized_pnl=5000,
            currency="USD",
            exchange="NASDAQ",
            sector="Technology",
            industry="Software",
            portfolio_weight=40,
            stock_type="mega_cap_quality",
            updated_at=utc_now(),
        ),
        Position(
            account_id="MOCK-001",
            symbol="JPM",
            company_name="JPMorgan",
            asset_class="STK",
            quantity=80,
            avg_cost=150,
            market_price=200,
            market_value=16000,
            unrealized_pnl=4000,
            currency="USD",
            exchange="NYSE",
            sector="Financials",
            industry="Banks",
            portfolio_weight=32,
            stock_type="mega_cap_quality",
            updated_at=utc_now(),
        ),
    ]
    from app.schemas.domain import AccountSummary, InvestmentPolicyStatement, InvestorProfile

    summary = AccountSummary(
        account_id="MOCK-001",
        net_liquidation=50000,
        cash=14000,
        buying_power=14000,
        margin_requirement=0,
        excess_liquidity=14000,
        total_unrealized_pnl=9000,
        total_realized_pnl=0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )
    policy = InvestmentPolicyStatement(
        target_equity_percent=80,
        target_cash_percent=20,
        target_bond_percent=0,
        minimum_cash=5000,
        max_single_stock_weight=60.0,
        max_sector_weight=80.0,
    )
    profile = InvestorProfile(
        objective="Growth",
        time_horizon_years=10,
        risk_tolerance="Medium",
        risk_capacity="Medium",
        liquidity_needs=0.1,
        net_worth_range="250k-1M",
        tax_residency="US",
        account_type="Taxable",
        restrictions=[],
    )
    proposal = generate_portfolio_optimization(positions, summary, policy, profile)
    assert proposal.proposed_trades
    assert proposal.methodology


def test_brinson_ledger_beginning_weights_from_transactions(monkeypatch):
    monkeypatch.setattr(
        "app.services.attribution.brinson_ledger._price_on_or_before",
        lambda symbol, _as_of, allow_mock=False: 300.0 if symbol == "MSFT" else 200.0,
    )
    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=10,
            price=300,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="JPM",
            trade_date=date(2024, 2, 1),
            action="buy",
            quantity=20,
            price=150,
            commission=0,
            currency="USD",
        ),
    ]
    positions = [
        Position(
            account_id="MOCK-001",
            symbol="MSFT",
            company_name="Microsoft",
            asset_class="STK",
            quantity=10,
            avg_cost=300,
            market_price=400,
            market_value=4000,
            unrealized_pnl=1000,
            currency="USD",
            exchange="NASDAQ",
            sector="Technology",
            industry="Software",
            portfolio_weight=50,
            stock_type="mega_cap_quality",
            updated_at=utc_now(),
        ),
        Position(
            account_id="MOCK-001",
            symbol="JPM",
            company_name="JPMorgan",
            asset_class="STK",
            quantity=20,
            avg_cost=150,
            market_price=200,
            market_value=4000,
            unrealized_pnl=1000,
            currency="USD",
            exchange="NYSE",
            sector="Financials",
            industry="Banks",
            portfolio_weight=50,
            stock_type="mega_cap_quality",
            updated_at=utc_now(),
        ),
    ]
    weights = beginning_sector_weights(
        transactions,
        positions,
        date(2024, 6, 1),
        "USD",
        lambda _from, _to, _as_of=None: 1.0,
        allow_mock=True,
    )
    assert weights
    returns = sector_returns_from_ledger(
        transactions,
        positions,
        date(2024, 6, 1),
        date(2024, 12, 31),
        allow_mock=True,
    )
    assert returns
