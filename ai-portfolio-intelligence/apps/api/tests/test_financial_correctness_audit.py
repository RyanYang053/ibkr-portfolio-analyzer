from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.domain import AccountSummary, Position
from app.services.data_quality.validation import validate_portfolio_snapshot
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.scoring.stock_score import score_stock
from app.services.technicals.indicators import calculate_technical_indicators


def _summary(net_liquidation: float = 100_000.0, cash: float = 20_000.0) -> AccountSummary:
    return AccountSummary(
        account_id="TEST",
        net_liquidation=net_liquidation,
        cash=cash,
        buying_power=50_000.0,
        margin_requirement=10_000.0,
        excess_liquidity=40_000.0,
        total_unrealized_pnl=0.0,
        total_realized_pnl=0.0,
        base_currency="USD",
        data_timestamp=datetime.now(timezone.utc),
    )


def _position(
    symbol: str,
    quantity: float,
    price: float,
    *,
    market_value: float | None = None,
    weight: float = 10.0,
    speculative: bool = False,
) -> Position:
    value = quantity * price if market_value is None else market_value
    return Position(
        account_id="TEST",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=quantity,
        avg_cost=price,
        market_price=price,
        market_value=value,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=weight,
        stock_type="speculative_growth" if speculative else "core",
        is_etf=False,
        is_speculative=speculative,
        updated_at=datetime.now(timezone.utc),
    )


def test_flat_price_series_has_neutral_rsi():
    indicators = calculate_technical_indicators("FLAT", [100.0] * 260)
    assert indicators.rsi_14 == 50.0
    assert indicators.macd == pytest.approx(0.0)
    assert indicators.macd_signal == pytest.approx(0.0)


def test_technical_pipeline_rejects_non_finite_and_non_positive_prices():
    with pytest.raises(ValueError):
        calculate_technical_indicators("BAD", [100.0] * 259 + [float("nan")])
    with pytest.raises(ValueError):
        calculate_technical_indicators("BAD", [100.0] * 259 + [0.0])


def test_data_quality_detects_position_arithmetic_and_reconciliation_errors():
    summary = _summary(net_liquidation=100_000.0, cash=10_000.0)
    position = _position("MSFT", 10.0, 100.0, market_value=50_000.0, weight=50.0)

    report = validate_portfolio_snapshot(summary, [position], fx_resolver=lambda _from, _to: 1.0)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["status"] == "fail"
    assert "POSITION_VALUE_MISMATCH" in codes
    assert "ACCOUNT_RECONCILIATION_GAP" in codes


def test_short_positions_do_not_cancel_gross_concentration():
    summary = _summary(net_liquidation=100_000.0, cash=100_000.0)
    positions = [
        _position("LONG", 500.0, 100.0, weight=50.0),
        _position("SHORT", -500.0, 100.0, weight=-50.0),
    ]

    risk = analyze_portfolio_risk(summary, positions)

    assert risk.top_5_concentration == pytest.approx(100.0)
    assert risk.herfindahl_concentration_score == pytest.approx(0.5)
    assert risk.single_stock_percent == pytest.approx(100.0)


def test_stock_score_does_not_claim_a_trained_model():
    from app.services.broker.mock_ibkr import MockIBKRAdapter

    adapter = MockIBKRAdapter()
    position = adapter.get_positions("MOCK-001")[0]
    score = score_stock(position, allow_mock=True)

    assert "gbdt" not in score.explanation.lower()
    assert "rule-based" in score.explanation.lower() or score.final_score is None
