from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db.daily_position_repo import upsert_daily_positions
from app.schemas.domain import Position, utc_now
from app.services.broker import ibkr_readonly
from app.services.broker.ibkr_readonly import CURRENT_FX_TTL_SECONDS, FxQuote, get_exchange_rate_quote
from app.services.market_data.fx_store import get_historical_exchange_rate


def test_current_fx_cache_expires(monkeypatch):
    calls = {"count": 0}

    def fake_fetch(pair: tuple[str, str]) -> FxQuote:
        calls["count"] += 1
        now = datetime.now(timezone.utc)
        return FxQuote(
            rate=1.25,
            source="yahoo_fx_live",
            observed_at=now,
            expires_at=now + timedelta(seconds=CURRENT_FX_TTL_SECONDS),
        )

    monkeypatch.setattr(ibkr_readonly, "_fetch_current_fx_quote", fake_fetch)
    with ibkr_readonly._fx_cache_lock:
        ibkr_readonly._fx_cache.clear()

    first = get_exchange_rate_quote("USD", "CAD")
    second = get_exchange_rate_quote("USD", "CAD")
    assert first.rate == second.rate == 1.25
    assert calls["count"] == 1

    expired = FxQuote(
        rate=1.25,
        source="yahoo_fx_live",
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with ibkr_readonly._fx_cache_lock:
        ibkr_readonly._fx_cache[("USD", "CAD")] = expired

    third = get_exchange_rate_quote("USD", "CAD")
    assert third.rate == 1.25
    assert calls["count"] == 2


def test_historical_fx_is_effective_dated(monkeypatch):
    captured: list[date] = []

    def fake_resolver(from_curr: str, to_curr: str, as_of: date) -> float:
        captured.append(as_of)
        return 1.1

    position = Position(
        account_id="U123",
        symbol="RY",
        company_name="Royal Bank",
        asset_class="STK",
        quantity=10,
        avg_cost=100,
        market_price=110,
        market_value=1100,
        unrealized_pnl=100,
        currency="CAD",
        exchange="TSE",
        sector="Financial",
        industry="Banks",
        portfolio_weight=5,
        stock_type="core",
        updated_at=utc_now(),
    )
    upsert_daily_positions(
        "U123",
        date(2026, 7, 10),
        [position],
        base_currency="USD",
        fx_resolver=fake_resolver,
    )
    assert captured == [date(2026, 7, 10)]


def test_resolver_signature_errors_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))

    position = Position(
        account_id="U123",
        symbol="RY",
        company_name="Royal Bank",
        asset_class="STK",
        quantity=10,
        avg_cost=100,
        market_price=110,
        market_value=1100,
        unrealized_pnl=100,
        currency="CAD",
        exchange="TSE",
        sector="Financial",
        industry="Banks",
        portfolio_weight=5,
        stock_type="core",
        updated_at=utc_now(),
    )

    with pytest.raises(TypeError):
        upsert_daily_positions(
            "U123",
            date(2026, 7, 10),
            [position],
            base_currency="USD",
            fx_resolver=lambda _from, _to: 1.0,
        )


def test_daily_position_rows_contain_fx_lineage(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))

    position = Position(
        account_id="U123",
        symbol="RY",
        company_name="Royal Bank",
        asset_class="STK",
        quantity=10,
        avg_cost=100,
        market_price=110,
        market_value=1100,
        unrealized_pnl=100,
        currency="CAD",
        exchange="TSE",
        sector="Financial",
        industry="Banks",
        portfolio_weight=5,
        stock_type="core",
        updated_at=utc_now(),
    )
    upsert_daily_positions(
        "U123",
        date(2026, 7, 10),
        [position],
        base_currency="USD",
        fx_resolver=lambda _from, _to, _as_of: 0.75,
    )

    from app.db.daily_position_repo import read_daily_positions

    rows = read_daily_positions("U123", date(2026, 7, 10))
    assert rows[0]["fx_rate_to_base"] == 0.75
    assert rows[0]["base_market_value"] == 825.0
    assert rows[0]["fx_source"] == "historical_fx_store"
    assert rows[0]["valuation_status"] == "available"


def test_get_historical_exchange_rate_requires_as_of_date():
    with pytest.raises(RuntimeError):
        get_historical_exchange_rate("USD", "CAD", date(1900, 1, 1))
