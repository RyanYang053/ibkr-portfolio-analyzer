from __future__ import annotations

from datetime import date

from app.services.fundamentals.providers import edgar_provider


def test_snapshot_populates_field_lineage(monkeypatch):
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "accn": "rev",
                            }
                        ]
                    }
                },
                "GrossProfit": {
                    "units": {
                        "USD": [
                            {
                                "val": 40.0,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                                "accn": "gp",
                            }
                        ]
                    }
                },
            }
        }
    }
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)
    snapshot = edgar_provider.fetch_edgar_fundamental_snapshot("TEST", as_of=date(2024, 6, 1))
    assert snapshot is not None
    assert "revenue" in snapshot.field_lineage
    assert snapshot.field_lineage["revenue"].metric == "revenue"
    assert snapshot.report_date == date(2023, 12, 31)
