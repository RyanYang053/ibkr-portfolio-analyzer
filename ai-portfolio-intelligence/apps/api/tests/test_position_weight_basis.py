"""Position weight must mean the same thing in demo mode and live mode.

The holdings table shows a weight next to an IPS limit ("max single stock
weight 12%"), and the policy engine checks that limit against net liquidation.
If the displayed weight used a different denominator, a user comparing the two
would read a breach that is not there — and the same portfolio would show
different weights in demo mode than live.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.broker.mock_ibkr import MockIBKRAdapter


@pytest.fixture()
def adapter(monkeypatch) -> MockIBKRAdapter:
    monkeypatch.setattr(settings, "broker_mode", "mock_ibkr_readonly")
    return MockIBKRAdapter()


@pytest.mark.parametrize("account_id", ["MOCK-001", "MOCK-002"])
def test_weight_is_a_share_of_net_liquidation(adapter, account_id):
    positions = adapter.get_positions(account_id)
    summary = adapter.get_account_summary(account_id)
    assert positions, "the mock portfolio must have holdings to weigh"

    for position in positions:
        expected = position.market_value / summary.net_liquidation * 100
        assert position.portfolio_weight == pytest.approx(expected, abs=0.02), (
            f"{position.symbol} weight {position.portfolio_weight} is not "
            f"{expected:.2f}% of net liquidation"
        )


@pytest.mark.parametrize("account_id", ["MOCK-001", "MOCK-002"])
def test_weights_plus_cash_account_for_the_whole_portfolio(adapter, account_id):
    """Weights must sum to the invested share, leaving exactly the cash share."""
    positions = adapter.get_positions(account_id)
    summary = adapter.get_account_summary(account_id)

    total_weight = sum(position.portfolio_weight for position in positions)
    cash_percent = summary.cash / summary.net_liquidation * 100

    assert total_weight + cash_percent == pytest.approx(100.0, abs=0.1)


@pytest.mark.parametrize("account_id", ["MOCK-001", "MOCK-002"])
def test_no_weight_exceeds_one_hundred_percent(adapter, account_id):
    for position in adapter.get_positions(account_id):
        assert 0 <= position.portfolio_weight <= 100


def test_summary_net_liquidation_is_holdings_plus_cash(adapter):
    """The identity every displayed percentage is derived from."""
    for account_id in ("MOCK-001", "MOCK-002"):
        positions = adapter.get_positions(account_id)
        summary = adapter.get_account_summary(account_id)
        invested = sum(position.market_value for position in positions)
        assert summary.net_liquidation == pytest.approx(invested + summary.cash, abs=0.01)
