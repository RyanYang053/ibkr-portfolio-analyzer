from datetime import date, datetime, timedelta, timezone

from app.db.scheduler_store import complete_job, job_already_completed, try_acquire_job


def test_scheduler_idempotency_json_backend(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    business_date = date(2026, 7, 10)
    assert try_acquire_job("scheduled_analysis", "MOCK-001", business_date, "morning:MOCK-001") is True
    assert try_acquire_job("scheduled_analysis", "MOCK-001", business_date, "morning:MOCK-001") is False
    complete_job("scheduled_analysis", "MOCK-001", business_date, "morning:MOCK-001", status="completed")
    assert job_already_completed("scheduled_analysis", "MOCK-001", business_date, "morning:MOCK-001") is True


def test_failed_scheduler_job_can_retry_after_backoff(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.core.config.settings.scheduler_max_attempts", 3)
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    business_date = date(2026, 7, 10)

    assert try_acquire_job("pnl_snapshot", "U123", business_date, "snapshot:U123") is True
    complete_job(
        "pnl_snapshot",
        "U123",
        business_date,
        "snapshot:U123",
        status="failed",
        error_message="broker unavailable",
    )
    assert try_acquire_job("pnl_snapshot", "U123", business_date, "snapshot:U123") is False

    from app.db.state_store import get_state_store

    key = "pnl_snapshot:U123:2026-07-10:snapshot:U123"
    store = get_state_store()
    record = store.read_json("scheduled_jobs", key, default={})
    record["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store.write_json("scheduled_jobs", key, record)

    assert try_acquire_job("pnl_snapshot", "U123", business_date, "snapshot:U123") is True
