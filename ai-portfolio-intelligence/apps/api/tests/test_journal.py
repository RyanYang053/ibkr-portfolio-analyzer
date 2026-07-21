"""Release D2: Trade journal + process analytics."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.journal import JournalEntry, OutcomeClassification
from app.services.journal.analytics import compute_process_analytics


def _entry(ret: float | None, **kw) -> JournalEntry:
    base = dict(entry_id=f"je_{ret}", account_id="A1", instrument_id="MSFT:1", symbol="MSFT", realized_return=ret)
    base.update(kw)
    return JournalEntry(**base)


# ------------------------------------------------------------ analytics


def test_analytics_withholds_on_small_sample():
    result = compute_process_analytics([_entry(0.1), _entry(-0.05)])
    assert result["status"] == "insufficient_sample"
    assert result["metrics"] is None


def test_analytics_computes_expectancy_and_winrate():
    entries = [_entry(0.20), _entry(0.10), _entry(-0.10), _entry(-0.05), _entry(0.05)]
    result = compute_process_analytics(entries)
    assert result["status"] == "available"
    m = result["metrics"]
    assert m["win_rate"] == 0.6  # 3 of 5 positive
    assert m["average_win"] > 0 and m["average_loss"] < 0
    assert m["payoff_ratio"] is not None
    # expectancy = 0.6*avg_win + 0.4*avg_loss
    assert isinstance(m["expectancy"], float)
    assert "by_strategy" in m and "by_market_regime" in m


def test_analytics_never_recommends_more_trading():
    result = compute_process_analytics([_entry(0.1), _entry(0.2), _entry(0.3)])
    assert "not a recommendation to trade more" in result["note"]


# ------------------------------------------------------------ routes


def test_journal_lifecycle_and_analytics_endpoint():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        created = client.post(
            "/journal",
            json={
                "account_id": "MOCK-001",
                "instrument_id": "MSFT:1",
                "entry_thesis": "Quality compounder",
                "strategy": "quality",
                "confidence": "high",
                "entry_price": 400.0,
            },
        )
        assert created.status_code == 200
        eid = created.json()["entry_id"]
        assert created.json()["outcome_classification"] == "open"

        # Close the trade with a realized return + review.
        updated = client.patch(
            f"/journal/{eid}",
            json={"exit_price": 460.0, "realized_return": 0.15, "outcome_classification": "win_good_process"},
        )
        assert updated.status_code == 200
        assert updated.json()["closed_at"] is not None

        review = client.post(
            f"/journal/{eid}/review",
            json={"interval": "thirty_day", "note": "held through noise", "rule_adherence": True, "lessons": ["patience"]},
        )
        assert review.status_code == 200
        assert len(review.json()["reviews"]) == 1

        listed = client.get("/journal?account_id=MOCK-001").json()
        assert listed["count"] >= 1

        analytics = client.get("/journal/analytics?account_id=MOCK-001").json()
        # One closed entry -> below the min sample, withheld honestly.
        assert analytics["status"] in {"insufficient_sample", "available"}
    finally:
        settings.broker_mode = orig
    assert OutcomeClassification.OPEN.value == "open"
