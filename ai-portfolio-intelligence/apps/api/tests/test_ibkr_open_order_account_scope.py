from __future__ import annotations

from types import SimpleNamespace

from app.services.broker.ibkr_readonly import IBKRReadOnlyAdapter


def test_open_orders_filter_by_actual_account(monkeypatch):
    adapter = IBKRReadOnlyAdapter()

    trade_a = SimpleNamespace(
        contract=SimpleNamespace(symbol="AAPL"),
        order=SimpleNamespace(action="BUY", totalQuantity=10, account="U111"),
        orderStatus=SimpleNamespace(status="Submitted", account="U111"),
    )
    trade_b = SimpleNamespace(
        contract=SimpleNamespace(symbol="MSFT"),
        order=SimpleNamespace(action="SELL", totalQuantity=5, account="U222"),
        orderStatus=SimpleNamespace(status="Submitted", account="U222"),
    )
    trade_unknown = SimpleNamespace(
        contract=SimpleNamespace(symbol="QQQ"),
        order=SimpleNamespace(action="BUY", totalQuantity=1, account=""),
        orderStatus=SimpleNamespace(status="Submitted", account=""),
    )

    class FakeIB:
        def openTrades(self):
            return [trade_a, trade_b, trade_unknown]

    monkeypatch.setattr(adapter, "_connect", lambda: _FakeContext(FakeIB()))

    orders = adapter.get_open_orders_readonly("U111")
    assert len(orders) == 1
    assert orders[0].account_id == "U111"
    assert orders[0].symbol == "AAPL"


class _FakeContext:
    def __init__(self, ib):
        self._ib = ib

    def __enter__(self):
        return self._ib

    def __exit__(self, exc_type, exc, tb):
        return False
