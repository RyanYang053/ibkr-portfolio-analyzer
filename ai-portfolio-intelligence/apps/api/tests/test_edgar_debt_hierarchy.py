from __future__ import annotations

from datetime import date

from app.services.fundamentals.concept_resolver import resolve_nonduplicative_debt
from app.services.fundamentals.providers import edgar_provider


def test_debt_hierarchy_avoids_double_counting_parent_and_child():
    payload = {
        "facts": {
            "us-gaap": {
                "LongTermDebtNoncurrent": {
                    "units": {"USD": [{"val": 500.0, "end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fy": 2023, "fp": "FY", "accn": "ltd"}]}
                },
                "ShortTermDebtCurrent": {
                    "units": {"USD": [{"val": 100.0, "end": "2023-12-31", "filed": "2024-02-01", "form": "10-K", "fy": 2023, "fp": "FY", "accn": "std"}]}
                },
            }
        }
    }
    total, lineage, exclusions = resolve_nonduplicative_debt(
        edgar_provider._latest_instant_value,
        payload,
        as_of=date(2024, 6, 1),
    )
    assert total == 600.0
    assert lineage is not None
    assert lineage.derivation == "hierarchy_sum"
    assert exclusions == []
