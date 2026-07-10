from datetime import date

from app.db.scheduler_store import complete_job, job_already_completed, try_acquire_job


def test_scheduler_idempotency_json_backend(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    business_date = date(2026, 7, 10)
    assert try_acquire_job("scheduled_analysis", None, business_date, "morning") is True
    assert try_acquire_job("scheduled_analysis", None, business_date, "morning") is False
    complete_job("scheduled_analysis", None, business_date, "morning", status="completed")
    assert job_already_completed("scheduled_analysis", None, business_date, "morning") is True
