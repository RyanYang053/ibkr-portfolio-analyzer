from __future__ import annotations

from app.services.fundamentals.providers import edgar_provider


def test_consecutive_four_quarter_sequences_require_adjacent_periods():
    rows = [
        {"unit": "USD", "value": 1.0, "end": "2023-03-31", "fp": "Q1"},
        {"unit": "USD", "value": 2.0, "end": "2023-06-30", "fp": "Q2"},
        {"unit": "USD", "value": 3.0, "end": "2023-09-30", "fp": "Q3"},
        {"unit": "USD", "value": 4.0, "end": "2023-12-31", "fp": "Q4"},
    ]
    sequences = edgar_provider.consecutive_four_quarter_sequences(rows)
    assert len(sequences) == 1
    assert sum(row["value"] for row in sequences[0]) == 10.0


def test_non_adjacent_quarters_do_not_form_sequence():
    rows = [
        {"unit": "USD", "value": 1.0, "end": "2023-03-31", "fp": "Q1"},
        {"unit": "USD", "value": 2.0, "end": "2023-06-30", "fp": "Q2"},
        {"unit": "USD", "value": 3.0, "end": "2024-09-30", "fp": "Q3"},
        {"unit": "USD", "value": 4.0, "end": "2024-12-31", "fp": "Q4"},
    ]
    sequences = edgar_provider.consecutive_four_quarter_sequences(rows)
    assert sequences == []
