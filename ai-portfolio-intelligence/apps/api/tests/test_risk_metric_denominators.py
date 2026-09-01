"""Each risk percentage is pinned to the base it is displayed against.

The UI shows concentration and exposure side by side. They use different
denominators on purpose — concentration is a share of invested capital, exposure
a share of net liquidation — and each stat card states which. These tests pin
that contract so a change to one metric cannot silently re-base it and turn the
displayed label into a lie.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.risk.portfolio_risk import analyze_portfolio_risk


@pytest.fixture()
def scenario(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")
    adapter = MockIBKRAdapter()
    positions = adapter.get_positions("MOCK-001")
    summary = adapter.get_account_summary("MOCK-001")
    risk = analyze_portfolio_risk(summary, positions)
    invested = sum(abs(p.market_value) for p in positions)
    return positions, summary, risk, invested


def test_cash_percent_is_of_net_liquidation(scenario):
    _, summary, risk, _ = scenario
    assert risk.cash_percent == pytest.approx(
        summary.cash / summary.net_liquidation * 100, abs=0.02
    )


@pytest.mark.parametrize(
    "field, predicate",
    [
        ("etf_percent", lambda p: p.is_etf),
        ("speculative_percent", lambda p: p.is_speculative),
        ("single_stock_percent", lambda p: not p.is_etf and p.asset_class not in {"OPT", "FOP"}),
    ],
)
def test_exposure_percentages_are_of_net_liquidation(scenario, field, predicate):
    positions, summary, risk, _ = scenario
    bucket = sum(abs(p.market_value) for p in positions if predicate(p))
    assert getattr(risk, field) == pytest.approx(
        bucket / summary.net_liquidation * 100, abs=0.02
    )


def test_margin_usage_is_of_net_liquidation(scenario):
    _, summary, risk, _ = scenario
    expected = max(0.0, summary.margin_requirement) / summary.net_liquidation * 100
    assert risk.margin_usage_percent == pytest.approx(expected, abs=0.02)


def test_top_five_concentration_is_of_invested_capital(scenario):
    positions, summary, risk, invested = scenario
    top5 = sum(sorted((abs(p.market_value) for p in positions), reverse=True)[:5])
    assert risk.top_5_concentration == pytest.approx(top5 / invested * 100, abs=0.02)
    # And is therefore not the net-liquidation figure, which is lower whenever
    # the account holds cash. Pinning the direction catches a silent re-base.
    assert risk.top_5_concentration > top5 / summary.net_liquidation * 100


def test_herfindahl_is_over_invested_weights(scenario):
    positions, _, risk, invested = scenario
    expected = sum((abs(p.market_value) / invested) ** 2 for p in positions)
    assert risk.herfindahl_concentration_score == pytest.approx(expected, abs=0.0005)
    # A concentration index must stay inside its theoretical bounds: 1/n for a
    # perfectly equal-weighted book, 1.0 for a single holding.
    assert 1 / len(positions) - 0.01 <= risk.herfindahl_concentration_score <= 1.0


def test_sector_exposure_is_a_share_of_invested_and_sums_to_one_hundred(scenario):
    positions, _, risk, invested = scenario
    by_sector: dict[str, float] = {}
    for position in positions:
        key = position.sector or "Unknown"
        by_sector[key] = by_sector.get(key, 0.0) + abs(position.market_value)

    for sector, value in by_sector.items():
        assert risk.sector_exposure[sector] == pytest.approx(
            value / invested * 100, abs=0.05
        )
    assert sum(risk.sector_exposure.values()) == pytest.approx(100.0, abs=0.1)


def test_unrealized_pnl_is_the_sum_of_positions(scenario):
    positions, summary, _, _ = scenario
    assert summary.total_unrealized_pnl == pytest.approx(
        sum(position.unrealized_pnl for position in positions), abs=0.01
    )
