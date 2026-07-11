from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.market_data.fx_store import HistoricalFxQuote, get_historical_fx_quote


def test_identity_fx_quote():
    quote = get_historical_fx_quote("USD", "USD", date(2026, 1, 15))
    assert isinstance(quote, HistoricalFxQuote)
    assert quote.rate == 1.0
    assert quote.source == "identity"
    assert quote.staleness_days == 0


def test_historical_fx_quote_has_metadata(monkeypatch):
    from app.services.market_data import fx_store

    monkeypatch.setattr(
        fx_store,
        "lookup_rate_with_metadata",
        lambda *_args, **_kwargs: HistoricalFxQuote(
            from_currency="EUR",
            to_currency="USD",
            rate=1.1,
            effective_date=date(2026, 1, 14),
            observed_at=datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc),
            source="test_source",
            staleness_days=1,
        ),
    )
    quote = get_historical_fx_quote("EUR", "USD", date(2026, 1, 15))
    assert quote.source == "test_source"
    assert quote.effective_date == date(2026, 1, 14)
    assert quote.staleness_days == 1
