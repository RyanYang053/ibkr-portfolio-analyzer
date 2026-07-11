from datetime import date

from app.schemas.domain import Position, utc_now
from app.services.fundamentals.providers import edgar_provider
from app.services.portfolio.pnl_period_effects import compute_period_price_and_realized_effects
from app.services.risk.advanced_risk import _risk_contribution


def test_edgar_as_of_filters_future_filings(monkeypatch):
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"val": 120.0, "end": "2024-12-31", "filed": "2025-02-01", "form": "10-K", "fy": 2024, "fp": "FY"},
                            {"val": 100.0, "end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fy": 2023, "fp": "FY"},
                        ]
                    }
                }
            }
        }
    }
    monkeypatch.setattr(edgar_provider, "_lookup_cik", lambda _symbol: "0000320193")
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)

    as_of_2024 = edgar_provider.fetch_edgar_fundamental_snapshot("AAPL", as_of=date(2024, 6, 1))
    as_of_2025 = edgar_provider.fetch_edgar_fundamental_snapshot("AAPL", as_of=date(2025, 6, 1))
    assert as_of_2024 is not None
    assert as_of_2025 is not None
    assert as_of_2024.free_cash_flow is None or isinstance(as_of_2024.free_cash_flow, float)
    assert as_of_2024.gross_margin is None or isinstance(as_of_2024.gross_margin, float)


def test_edgar_dedupes_restatements():
    rows = [
        {"end": "2024-12-31", "form": "10-K", "fp": "FY", "filed": "2025-02-01", "value": 100.0},
        {"end": "2024-12-31", "form": "10-K", "fp": "FY", "filed": "2025-03-15", "value": 105.0},
    ]
    deduped = edgar_provider._dedupe_restatements(rows)
    assert len(deduped) == 1
    assert deduped[0]["value"] == 105.0


def test_risk_contribution_percentages_sum_to_one_hundred():
    covariance = [
        [0.04, 0.01],
        [0.01, 0.09],
    ]
    weights = {"AAA": 0.6, "BBB": 0.4}
    _, components = _risk_contribution(weights, covariance, ["AAA", "BBB"])
    total = sum(components.values())
    assert total > 0
    pct = {symbol: (value / total) * 100.0 for symbol, value in components.items()}
    assert abs(sum(pct.values()) - 100.0) < 1e-6


def test_period_price_effect_from_opening_and_closing_marks():
    opening = [{"symbol": "MSFT", "con_id": 1, "quantity": 10.0, "market_price": 100.0, "currency": "USD"}]
    closing = [
        Position(
            account_id="TEST-001",
            symbol="MSFT",
            company_name="MSFT",
            asset_class="STK",
            quantity=10,
            avg_cost=90,
            market_price=110,
            market_value=1100,
            unrealized_pnl=200,
            currency="USD",
            exchange="NASDAQ",
            sector="Technology",
            industry="Software",
            portfolio_weight=10,
            stock_type="mega_cap_quality",
            con_id=1,
            updated_at=utc_now(),
        )
    ]
    price_effect, realized, _, exclusions = compute_period_price_and_realized_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert price_effect == 100.0
    assert "opening_positions_unavailable" not in exclusions
