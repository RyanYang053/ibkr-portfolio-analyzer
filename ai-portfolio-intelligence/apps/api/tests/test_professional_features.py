import os
import pytest
from datetime import date, datetime, timezone
from app.schemas.domain import (
    AccountSummary,
    Position,
    InvestorProfile,
    InvestmentPolicyStatement,
    utc_now
)
from app.services.suitability.engine import (
    get_investor_profile,
    save_investor_profile,
    check_position_suitability,
    check_recommendation_suitability
)
from app.services.policy.engine import (
    get_portfolio_policy,
    save_portfolio_policy,
    analyze_policy_drift
)
from app.services.portfolio_construction.engine import generate_rebalance_proposal
from app.services.risk.advanced_risk import calculate_advanced_risk_metrics
from app.services.attribution.engine import calculate_performance_attribution
from app.services.guardrails.engine import (
    apply_recommendation_guardrails,
    append_compliance_disclaimer,
    ROBO_DISCLOSURE
)

def _make_mock_summary(net_liq=150000.0, cash=25000.0) -> AccountSummary:
    return AccountSummary(
        account_id="TEST-001",
        net_liquidation=net_liq,
        cash=cash,
        buying_power=80000.0,
        margin_requirement=15000.0,
        excess_liquidity=65000.0,
        total_unrealized_pnl=5000.0,
        total_realized_pnl=1000.0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )

def _make_mock_position(symbol, qty, weight, is_spec=False, is_etf=False, sector="Technology") -> Position:
    return Position(
        account_id="TEST-001",
        symbol=symbol,
        company_name=f"{symbol} Inc.",
        asset_class="STK",
        quantity=qty,
        avg_cost=100.0,
        market_price=110.0,
        market_value=qty * 110.0,
        unrealized_pnl=qty * 10.0,
        realized_pnl=0.0,
        currency="USD",
        exchange="SMART",
        sector=sector,
        industry="Misc",
        portfolio_weight=weight,
        stock_type="speculative_growth" if is_spec else "core",
        is_etf=is_etf,
        is_speculative=is_spec,
        updated_at=utc_now(),
    )


def test_suitability_rules():
    # Test suitability checks
    profile = InvestorProfile(
        objective="Capital Preservation",
        time_horizon_years=2,
        risk_tolerance="Low",
        risk_capacity="Medium",
        liquidity_needs=20000.0,
        net_worth_range="100k-500k",
        tax_residency="Canada",
        account_type="Tax-Free",
        restrictions=["CELH"]
    )
    
    spec_pos = _make_mock_position("IONQ", qty=100, weight=5.0, is_spec=True)
    warnings = check_position_suitability(profile, spec_pos)
    
    assert any("unsuitable for Low Risk Tolerance" in w for w in warnings)
    assert any("unsuitable for Capital Preservation" in w for w in warnings)
    assert any("short time horizon" in w for w in warnings)
    assert any("excessive concentration" in w for w in warnings) # weight 5.0 > 3.0 limit
    
    restricted_pos = _make_mock_position("CELH", qty=10, weight=1.0)
    res_warnings = check_position_suitability(profile, restricted_pos)
    assert any("violates explicit investment restriction" in w for w in res_warnings)


def test_policy_drift_analysis():
    policy = InvestmentPolicyStatement(
        target_equity_percent=80.0,
        target_cash_percent=20.0,
        target_bond_percent=0.0,
        max_single_stock_weight=10.0,
        max_speculative_weight=4.0,
        max_sector_weight=30.0,
        minimum_cash=10000.0,
        benchmark="SPY",
        rebalancing_drift_threshold=5.0
    )
    
    positions = [
        _make_mock_position("AAPL", qty=136, weight=15.0), # single concentration limit exceeded (15 > 10)
        _make_mock_position("IONQ", qty=55, weight=6.0, is_spec=True), # spec limit exceeded (6 > 4)
        _make_mock_position("MSFT", qty=318, weight=35.0, sector="Technology"), # tech sector limit exceeded (35 + 15 + 6 > 30)
    ]
    
    # Total portfolio val = 100k, cash = 44k (44%), equities = 56%
    drift = analyze_policy_drift(positions, cash=44000.0, total_val=100000.0, policy=policy)
    
    assert drift["rebalance_triggered"] is True
    assert any("Equity" in w and "drift" in w for w in drift["warnings"])
    assert any("single stock concentration in aapl" in w.lower() for w in drift["warnings"])
    assert any("speculative asset concentration" in w.lower() for w in drift["warnings"])
    assert any("sector concentration in technology" in w.lower() for w in drift["warnings"])


def test_rebalancing_solver():
    profile = InvestorProfile(
        objective="Growth",
        time_horizon_years=10,
        risk_tolerance="High",
        risk_capacity="High",
        liquidity_needs=5000.0,
        net_worth_range="100k-500k",
        tax_residency="Canada",
        account_type="Taxable",
        restrictions=[]
    )
    
    policy = InvestmentPolicyStatement(
        target_equity_percent=80.0,
        target_cash_percent=20.0,
        target_bond_percent=0.0,
        max_single_stock_weight=10.0,
        max_speculative_weight=5.0,
        minimum_cash=10000.0,
        benchmark="SPY",
        rebalancing_drift_threshold=5.0
    )
    
    positions = [
        _make_mock_position("AAPL", qty=136, weight=15.0), # overweight single stock
        _make_mock_position("IONQ", qty=73, weight=8.0, is_spec=True), # overweight speculative
    ]
    summary = _make_mock_summary(net_liq=100000.0, cash=5000.0) # cash 5k is below cash floor of 20k target
    
    proposal = generate_rebalance_proposal(positions, summary, policy, profile)
    
    assert len(proposal.proposed_trades) > 0
    # Must propose sells to raise cash and fix concentration
    sells = [t for t in proposal.proposed_trades if t.action == "Sell"]
    assert len(sells) > 0
    assert any(t.symbol == "AAPL" for t in sells)
    assert any(t.symbol == "IONQ" for t in sells)
    assert "may realize gains or losses" in proposal.tax_impact_warning


def test_advanced_risk_and_stress_tests():
    positions = [
        _make_mock_position("MSFT", qty=100, weight=40.0),
        _make_mock_position("QQQ", qty=100, weight=40.0, is_etf=True),
        _make_mock_position("IONQ", qty=100, weight=20.0, is_spec=True),
    ]
    summary = _make_mock_summary(net_liq=100000.0)
    
    # 3 days of historical prices
    from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
    history = [
        PortfolioPnLSnapshot(date="2026-06-08", timestamp="...", net_liquidation=100000.0, cash=5000.0, buying_power=0.0, margin_requirement=0.0, daily_pnl=0.0, daily_pnl_percent=0.0, positions=[]),
        PortfolioPnLSnapshot(date="2026-06-09", timestamp="...", net_liquidation=98000.0, cash=5000.0, buying_power=0.0, margin_requirement=0.0, daily_pnl=-2000.0, daily_pnl_percent=-2.0, positions=[]),
        PortfolioPnLSnapshot(date="2026-06-10", timestamp="...", net_liquidation=101000.0, cash=5000.0, buying_power=0.0, margin_requirement=0.0, daily_pnl=3000.0, daily_pnl_percent=3.0, positions=[]),
    ]
    
    risk_metrics = calculate_advanced_risk_metrics(positions, summary, history)
    
    # Historical metrics fail closed without a complete external-cash-flow ledger.
    assert risk_metrics.max_drawdown is None
    assert risk_metrics.volatility is None
    assert risk_metrics.portfolio_beta_spy is None
    assert risk_metrics.data_quality["historical_metrics"] == "insufficient"
    assert risk_metrics.data_quality["cash_flow_ledger"] == "missing"
    assert len(risk_metrics.stress_tests) == 4
    
    rate_shock = next(t for t in risk_metrics.stress_tests if "rate shock" in t.name)
    assert rate_shock.portfolio_change_pct < 0.0


def test_performance_attribution():
    positions = [
        _make_mock_position("MSFT", qty=100, weight=50.0),
        _make_mock_position("SPY", qty=100, weight=50.0, is_etf=True),
    ]
    
    # Mock unrealized pnl is 1000 for each (avg_cost=100, market_price=110, qty=100)
    attribution = calculate_performance_attribution(positions, [])
    
    assert attribution.security_selection_pnl["MSFT"] == 1000.0
    assert attribution.asset_class_pnl["Single Stock"] == 1000.0
    assert attribution.asset_class_pnl["ETF"] == 1000.0
    assert attribution.benchmark_relative_alpha is None


def test_guardrails_and_compliance():
    # Suitability warning should trigger trim override
    warnings = ["Speculative position IONQ has excessive concentration"]
    action, reason = apply_recommendation_guardrails("Add", "IONQ", warnings)
    
    assert action == "Trim Review"
    assert "Override" in reason
    
    # Compliance disclaimer injection
    report = {
        "summary": "This is a great stock buy zone.",
        "holdings": []
    }
    secured = append_compliance_disclaimer(report)
    assert "disclaimer" in secured
    assert secured["robo_advisor_disclosure"] == ROBO_DISCLOSURE
    assert secured["human_review_required"] is True
