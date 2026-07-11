from __future__ import annotations

from app.services.fundamentals.providers import edgar_provider


def test_negative_quarter_values_are_allowed():
    rows = [
        {
            "concept": "NetIncomeLoss",
            "unit": "USD",
            "value": -10.0,
            "start": "2023-01-01",
            "end": "2023-03-31",
            "filed": "2023-05-01",
            "fy": 2023,
            "fp": "Q1",
        },
        {
            "concept": "NetIncomeLoss",
            "unit": "USD",
            "value": 30.0,
            "start": "2023-04-01",
            "end": "2023-06-30",
            "filed": "2023-08-01",
            "fy": 2023,
            "fp": "Q2",
        },
        {
            "concept": "NetIncomeLoss",
            "unit": "USD",
            "value": 20.0,
            "start": "2023-07-01",
            "end": "2023-09-30",
            "filed": "2023-11-01",
            "fy": 2023,
            "fp": "Q3",
        },
        {
            "concept": "NetIncomeLoss",
            "unit": "USD",
            "value": 10.0,
            "start": "2023-10-01",
            "end": "2023-12-31",
            "filed": "2024-02-01",
            "fy": 2023,
            "fp": "Q4",
        },
    ]
    quarters = edgar_provider._standalone_quarters_for_fy(rows, 2023)
    assert quarters is not None
    assert quarters["Q1"] == -10.0
    assert sum(quarters.values()) == 50.0
