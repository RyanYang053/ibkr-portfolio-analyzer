import pytest

from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.portfolio.account_scope import find_portfolio_position


def test_find_position_by_con_id_requires_account():
    adapter = MockIBKRAdapter()
    with pytest.raises(Exception):
        find_portfolio_position("AAPL", adapter, con_id=12345)


def test_find_position_by_con_id_within_account():
    adapter = MockIBKRAdapter()
    position = find_portfolio_position("MSFT", adapter, account_id="MOCK-001", con_id=272093)
    assert position is not None
    assert position.con_id == 272093


def test_find_position_without_account_scope_does_not_search_all_accounts():
    adapter = MockIBKRAdapter()
    assert find_portfolio_position("AAPL", adapter) is None
