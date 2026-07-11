from __future__ import annotations

from datetime import date

from app.services.fundamentals.providers import edgar_provider


def _quarter_row(value, fp, start, end, filed, fy, accn):
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


def _annual_row(value, end, filed, fy, accn="fy"):
    end_date = date.fromisoformat(end)
    start = end_date.replace(year=end_date.year - 1).isoformat()
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


def _payload(concept, rows):
    return {"facts": {"us-gaap": {concept: {"units": {"USD": rows}}}}}


def test_latest_rolling_ttm_prefers_newer_quarters_over_older_annual():
    payload = _payload(
        "Revenues",
        [
            _annual_row(90.0, "2022-12-31", "2023-02-01", 2022),
            _annual_row(100.0, "2023-12-31", "2024-02-01", 2023),
            _quarter_row(30, "Q1", "2024-01-01", "2024-03-31", "2024-05-01", 2024, "n1"),
            _quarter_row(30, "Q2", "2024-04-01", "2024-06-30", "2024-08-01", 2024, "n2"),
            _quarter_row(30, "Q3", "2024-07-01", "2024-09-30", "2024-11-01", 2024, "n3"),
            _quarter_row(30, "Q4", "2024-10-01", "2024-12-31", "2025-02-01", 2024, "n4"),
        ],
    )
    value, sources = edgar_provider._latest_ttm_duration_value(payload, "Revenues", as_of=date(2025, 6, 1))
    assert value == 120.0
    assert len(sources) == 4


def test_latest_rolling_ttm_falls_back_to_annual_when_no_quarter_sequence():
    payload = _payload(
        "Revenues",
        [
            _annual_row(100.0, "2023-12-31", "2024-02-01", 2023),
        ],
    )
    value, _ = edgar_provider._latest_ttm_duration_value(payload, "Revenues", as_of=date(2024, 6, 1))
    assert value == 100.0
