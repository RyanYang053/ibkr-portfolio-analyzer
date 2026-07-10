from datetime import date

from app.db.scheduler_store import complete_job, try_acquire_job


def test_scheduler_concurrent_claim_only_one_worker_wins(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    business_date = date(2026, 7, 11)
    first = try_acquire_job("scheduled_analysis", "U123", business_date, "morning")
    second = try_acquire_job("scheduled_analysis", "U123", business_date, "morning")
    assert first is True
    assert second is False
    complete_job("scheduled_analysis", "U123", business_date, "morning", status="completed")
    third = try_acquire_job("scheduled_analysis", "U123", business_date, "morning")
    assert third is False
