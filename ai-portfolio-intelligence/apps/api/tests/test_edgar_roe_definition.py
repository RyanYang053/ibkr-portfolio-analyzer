from __future__ import annotations

from datetime import date

from app.services.fundamentals.providers import edgar_provider


def test_roe_uses_net_income_over_average_equity(monkeypatch):
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 400.0,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                            }
                        ]
                    }
                },
                "NetIncomeLossAvailableToCommonStockholdersBasic": {
                    "units": {
                        "USD": [
                            {
                                "val": 20.0,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                            }
                        ]
                    }
                },
                "CommonStockholdersEquity": {
                    "units": {
                        "USD": [
                            {"val": 80.0, "end": "2022-12-31", "filed": "2023-02-01", "form": "10-K", "fy": 2022, "fp": "FY"},
                            {"val": 120.0, "end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fy": 2023, "fp": "FY"},
                        ]
                    }
                },
            }
        }
    }
    monkeypatch.setattr(edgar_provider, "fetch_company_facts_payload", lambda _symbol: payload)
    snapshot = edgar_provider.fetch_edgar_fundamental_snapshot("TEST", as_of=date(2024, 6, 1))
    assert snapshot is not None
    assert snapshot.return_on_equity == round(20.0 / 100.0, 4)
