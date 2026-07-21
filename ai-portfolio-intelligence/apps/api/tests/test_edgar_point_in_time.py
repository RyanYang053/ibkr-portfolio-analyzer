from __future__ import annotations

from datetime import date

import pytest

from app.services.fundamentals.providers import edgar_provider


def _annual_row(
    value: float,
    *,
    end: str,
    filed: str,
    fy: int,
    accn: str = "0001",
    start: str | None = None,
) -> dict:
    if start is None:
        end_date = date.fromisoformat(end)
        start = (end_date.replace(year=end_date.year - 1)).isoformat()
    return {
        "val": value,
        "start": start,
        "end": end,
        "filed": filed,
        "form": "10-K",
        "fy": fy,
        "fp": "FY",
        "accn": accn,
        "frame": f"CY{fy}",
    }


def _quarter_row(
    value: float,
    *,
    fp: str,
    end: str,
    filed: str,
    fy: int,
    start: str,
    accn: str,
) -> dict:
    return {
        "val": value,
        "start": start,
        "end": end,
        "filed": filed,
        "form": "10-Q",
        "fy": fy,
        "fp": fp,
        "accn": accn,
        "frame": f"CY{fy}{fp}",
    }


def _payload(concept: str, rows: list[dict], *, unit: str = "USD") -> dict:
    return {"facts": {"us-gaap": {concept: {"units": {unit: rows}}}}}


def test_rows_as_of_excludes_future_restatement():
    rows = edgar_provider._point_in_time_values(
        _payload(
            "Revenues",
            [
                _annual_row(100.0, end="2023-12-31", filed="2024-02-01", fy=2023, accn="orig"),
                _annual_row(110.0, end="2023-12-31", filed="2025-02-01", fy=2023, accn="restated"),
            ],
        ),
        "Revenues",
    )
    as_of_original = edgar_provider._rows_as_of(rows, date(2024, 6, 1))
    assert len(as_of_original) == 1
    assert as_of_original[0]["value"] == 100.0
    assert as_of_original[0]["accn"] == "orig"

    as_of_restatement = edgar_provider._rows_as_of(rows, date(2025, 6, 1))
    assert as_of_restatement[0]["value"] == 110.0
    assert as_of_restatement[0]["accn"] == "restated"


def test_ttm_prefers_latest_annual_fact():
    payload = _payload(
        "Revenues",
        [
            _annual_row(90.0, end="2022-12-31", filed="2023-02-01", fy=2022),
            _annual_row(100.0, end="2023-12-31", filed="2024-02-01", fy=2023),
        ],
    )
    value, source = edgar_provider._ttm_duration_value(payload, "Revenues", as_of=date(2024, 6, 1))
    assert value == 100.0
    assert source["accn"] is not None


def test_ttm_sums_four_standalone_quarters():
    payload = _payload(
        "Revenues",
        [
            _quarter_row(10, fp="Q1", start="2023-01-01", end="2023-03-31", filed="2023-05-01", fy=2023, accn="q1"),
            _quarter_row(20, fp="Q2", start="2023-04-01", end="2023-06-30", filed="2023-08-01", fy=2023, accn="q2"),
            _quarter_row(30, fp="Q3", start="2023-07-01", end="2023-09-30", filed="2023-11-01", fy=2023, accn="q3"),
            _quarter_row(40, fp="Q4", start="2023-10-01", end="2023-12-31", filed="2024-02-01", fy=2023, accn="q4"),
        ],
    )
    value, _ = edgar_provider._ttm_duration_value(payload, "Revenues", as_of=date(2024, 6, 1))
    assert value == 100.0


def test_ttm_derives_quarters_from_ytd_facts():
    payload = _payload(
        "Revenues",
        [
            _quarter_row(25, fp="Q1", start="2023-01-01", end="2023-03-31", filed="2023-05-01", fy=2023, accn="q1"),
            {
                "val": 55,
                "start": "2023-01-01",
                "end": "2023-06-30",
                "filed": "2023-08-01",
                "form": "10-Q",
                "fy": 2023,
                "fp": "Q2",
                "accn": "h1",
                "frame": "CY2023Q2",
            },
            {
                "val": 80,
                "start": "2023-01-01",
                "end": "2023-09-30",
                "filed": "2023-11-01",
                "form": "10-Q",
                "fy": 2023,
                "fp": "Q3",
                "accn": "9m",
                "frame": "CY2023Q3",
            },
            _annual_row(100.0, end="2023-12-31", filed="2024-02-01", fy=2023, accn="fy"),
        ],
    )
    quarters = edgar_provider._standalone_quarters_for_fy(
        edgar_provider._rows_as_of(edgar_provider._point_in_time_values(payload, "Revenues"), date(2024, 6, 1)),
        2023,
    )
    assert {fp: row["value"] for fp, row in quarters.items()} == {
        "Q1": 25.0,
        "Q2": 30.0,
        "Q3": 25.0,
        "Q4": 20.0,
    }


def test_ttm_returns_none_when_no_single_unit_has_complete_history():
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _quarter_row(10, fp="Q1", start="2023-01-01", end="2023-03-31", filed="2023-05-01", fy=2023, accn="u1"),
                            _quarter_row(20, fp="Q2", start="2023-04-01", end="2023-06-30", filed="2023-08-01", fy=2023, accn="u2"),
                        ],
                        "EUR": [
                            _quarter_row(30, fp="Q3", start="2023-07-01", end="2023-09-30", filed="2023-11-01", fy=2023, accn="e1"),
                            _quarter_row(40, fp="Q4", start="2023-10-01", end="2023-12-31", filed="2024-02-01", fy=2023, accn="e2"),
                        ],
                    }
                }
            }
        }
    }
    value, _ = edgar_provider._ttm_duration_value(payload, "Revenues", as_of=date(2024, 6, 1))
    assert value is None


def test_snapshot_withholds_fcf_when_capex_missing(monkeypatch):
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [_annual_row(100.0, end="2023-12-31", filed="2024-02-01", fy=2023)]}},
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [_annual_row(40.0, end="2023-12-31", filed="2024-02-01", fy=2023, accn="ocf")]}
                },
            }
        }
    }
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)
    snapshot = edgar_provider.fetch_edgar_fundamental_snapshot("TEST")
    assert snapshot is not None
    assert snapshot.operating_cash_flow == 40.0
    assert snapshot.free_cash_flow is None


def test_latest_instant_value_uses_balance_sheet_fact(monkeypatch):
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [_annual_row(100.0, end="2023-12-31", filed="2024-02-01", fy=2023)]}},
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {"val": 5.0, "end": "2023-06-30", "filed": "2023-08-01", "form": "10-Q", "fy": 2023, "fp": "Q2"},
                            {"val": 8.0, "end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fy": 2023, "fp": "FY"},
                        ]
                    }
                },
            }
        }
    }
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)
    snapshot = edgar_provider.fetch_edgar_fundamental_snapshot("TEST", as_of=date(2024, 6, 1))
    assert snapshot is not None
    assert snapshot.cash == 8.0


def test_missing_us_gaap_concept_returns_none(monkeypatch):
    payload = {"facts": {"ifrs-full": {}}}
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)
    assert edgar_provider.fetch_edgar_fundamental_snapshot("FOREIGN") is None


def test_production_requires_real_sec_user_agent(monkeypatch):
    from app.core.config import validate_production_settings

    monkeypatch.setattr("app.core.config.settings.environment", "production")
    monkeypatch.setattr("app.core.config.settings.sec_edgar_user_agent", "PortfolioIntelligence/1.0 contact@example.com")
    with pytest.raises(RuntimeError, match="SEC EDGAR"):
        validate_production_settings()
