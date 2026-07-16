from __future__ import annotations

from datetime import date

from app.schemas.domain import Position, Transaction, utc_now
from app.services.portfolio.pnl_period_effects import compute_period_effects


def _position(symbol: str, qty: float, price: float, con_id: int) -> Position:
    return Position(
        account_id="TEST-001",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=qty,
        avg_cost=price,
        market_price=price,
        market_value=qty * price,
        unrealized_pnl=0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=5,
        stock_type="core",
        con_id=con_id,
        updated_at=utc_now(),
    )


def _txn(
    symbol: str,
    action: str,
    quantity: float,
    price: float,
    *,
    con_id: int | None = None,
    trade_date: date = date(2026, 1, 15),
) -> Transaction:
    return Transaction(
        account_id="TEST-001",
        symbol=symbol,
        trade_date=trade_date,
        action=action,
        quantity=quantity,
        price=price,
        commission=0,
        currency="USD",
        source="test",
        con_id=con_id,
    )


def test_union_includes_opened_position_as_reconciled_when_buy_explains_quantity(monkeypatch):
    opening = [{"symbol": "AAA", "con_id": 1, "quantity": 10.0, "market_price": 100.0, "currency": "USD"}]
    closing = [
        _position("AAA", 10, 110, 1),
        _position("BBB", 5, 50, 2),
    ]
    monkeypatch.setattr(
        "app.services.portfolio.pnl_period_effects.get_transactions",
        lambda _account_id: [_txn("BBB", "buy", 5, 50, con_id=2)],
    )
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert "position_universe_change_reconciled:BBB:2" in effects.exclusions
    assert effects.complete is True
    assert effects.price_effect is not None


def test_complete_exit_reconciled_when_sell_explains_quantity(monkeypatch):
    opening = [
        {
            "symbol": "CCC",
            "con_id": 3,
            "quantity": 8.0,
            "market_price": 40.0,
            "local_price": 40.0,
            "currency": "USD",
            "multiplier": 1.0,
        }
    ]
    closing: list[Position] = []
    monkeypatch.setattr(
        "app.services.portfolio.pnl_period_effects.get_transactions",
        lambda _account_id: [_txn("CCC", "sell", 8, 42, con_id=3)],
    )
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert "position_universe_change_reconciled:CCC:3" in effects.exclusions
    assert effects.complete is True


def test_unexplained_closing_quantity_marks_period_incomplete(monkeypatch):
    opening = [
        {
            "symbol": "AAA",
            "con_id": 1,
            "quantity": 10.0,
            "market_price": 100.0,
            "local_price": 100.0,
            "currency": "USD",
            "multiplier": 1.0,
        }
    ]
    closing = [_position("AAA", 20, 110, 1)]

    monkeypatch.setattr(
        "app.services.portfolio.pnl_period_effects.get_transactions",
        lambda _account_id: [],
    )

    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda *_args: 1.0,
    )

    assert effects.complete is False
    assert any(
        item.startswith("quantity_bridge_mismatch:AAA:1")
        for item in effects.exclusions
    )


def test_quantity_bridge_complete_after_buy(monkeypatch):
    opening = [
        {
            "symbol": "AAA",
            "con_id": 1,
            "quantity": 10.0,
            "market_price": 100.0,
            "local_price": 100.0,
            "currency": "USD",
            "multiplier": 1.0,
        }
    ]
    closing = [_position("AAA", 15, 110, 1)]
    monkeypatch.setattr(
        "app.services.portfolio.pnl_period_effects.get_transactions",
        lambda _account_id: [_txn("AAA", "buy", 5, 105, con_id=1)],
    )
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda *_args: 1.0,
    )
    assert effects.complete is True
    assert not any(item.startswith("quantity_bridge_mismatch:") for item in effects.exclusions)


def test_quantity_bridge_complete_after_long_to_short(monkeypatch):
    opening = [
        {
            "symbol": "AAA",
            "con_id": 1,
            "quantity": 10.0,
            "market_price": 100.0,
            "local_price": 100.0,
            "currency": "USD",
            "multiplier": 1.0,
        }
    ]
    closing = [_position("AAA", -5, 110, 1)]
    monkeypatch.setattr(
        "app.services.portfolio.pnl_period_effects.get_transactions",
        lambda _account_id: [_txn("AAA", "sell", 15, 105, con_id=1)],
    )
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda *_args: 1.0,
    )
    assert effects.complete is True
    assert not any(item.startswith("quantity_bridge_mismatch:") for item in effects.exclusions)


def test_quantity_bridge_complete_after_partial_short_cover(monkeypatch):
    opening = [
        {
            "symbol": "AAA",
            "con_id": 1,
            "quantity": -10.0,
            "market_price": 100.0,
            "local_price": 100.0,
            "currency": "USD",
            "multiplier": 1.0,
        }
    ]
    closing = [_position("AAA", -5, 90, 1)]
    monkeypatch.setattr(
        "app.services.portfolio.pnl_period_effects.get_transactions",
        lambda _account_id: [_txn("AAA", "buy", 5, 95, con_id=1)],
    )
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda *_args: 1.0,
    )
    assert effects.complete is True
    assert not any(item.startswith("quantity_bridge_mismatch:") for item in effects.exclusions)


def test_missing_opening_market_price_withholds_price_effect():
    opening = [{"symbol": "AAA", "con_id": 1, "quantity": 10.0, "currency": "USD"}]
    closing = [_position("AAA", 10, 110, 1)]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert any("opening_market_price_missing" in item for item in effects.exclusions)
    assert effects.complete is False
