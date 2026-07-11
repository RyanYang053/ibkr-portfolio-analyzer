from __future__ import annotations

from datetime import date

from app.services.fundamentals.providers import edgar_provider


def test_restatement_respected_at_as_of_date():
    rows = edgar_provider._point_in_time_values(
        {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "val": 100.0,
                                    "start": "2022-01-01",
                                    "end": "2022-12-31",
                                    "filed": "2023-02-01",
                                    "form": "10-K",
                                    "fy": 2022,
                                    "fp": "FY",
                                    "accn": "orig",
                                },
                                {
                                    "val": 110.0,
                                    "start": "2022-01-01",
                                    "end": "2022-12-31",
                                    "filed": "2025-02-01",
                                    "form": "10-K",
                                    "fy": 2022,
                                    "fp": "FY",
                                    "accn": "restated",
                                },
                            ]
                        }
                    }
                }
            }
        },
        "Revenues",
    )
    original = edgar_provider._rows_as_of(rows, date(2024, 1, 1))
    restated = edgar_provider._rows_as_of(rows, date(2025, 6, 1))
    assert original[0]["value"] == 100.0
    assert restated[0]["value"] == 110.0
