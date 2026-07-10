from __future__ import annotations

from datetime import date

import pytest

from app.db.scheduler_store import complete_job, try_acquire_job
from app.services.scheduler_lease import SchedulerLeaseHeartbeat, SchedulerLeaseLost


def test_scheduler_lease_loss_aborts_on_failed_renewal(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.scheduler_lease_minutes", 1)
    monkeypatch.setattr(
        "app.services.scheduler_lease.renew_job_lease",
        lambda *args, **kwargs: False,
    )

    with pytest.raises(SchedulerLeaseLost, match="ownership was lost"):
        with SchedulerLeaseHeartbeat("scheduled_analysis", "U123", date(2026, 7, 10), "morning:U123") as lease:
            lease.assert_owned()


def test_scheduler_lease_loss_aborts_on_renewal_exception(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.services.scheduler_lease.renew_job_lease", boom)

    with pytest.raises(SchedulerLeaseLost, match="renewal failed"):
        with SchedulerLeaseHeartbeat("scheduled_analysis", "U123", date(2026, 7, 10), "morning:U123"):
            pass


def test_stale_worker_cannot_complete_after_fencing_token_change(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    business_date = date(2026, 7, 10)

    assert try_acquire_job("scheduled_analysis", "U123", business_date, "morning:U123") is True

    from app.db import scheduler_store
    from app.db.state_store import get_state_store

    stale_claim = scheduler_store._active_claims.copy()
    key = "scheduled_analysis:U123:2026-07-10:morning:U123"
    store = get_state_store()
    record = store.read_json("scheduled_jobs", key, default={})
    record["fencing_token"] = int(record.get("fencing_token", 1)) + 1
    record["worker_id"] = "other-host:99999"
    store.write_json("scheduled_jobs", key, record)

    scheduler_store._active_claims.clear()
    scheduler_store._active_claims.update(stale_claim)
    assert complete_job("scheduled_analysis", "U123", business_date, "morning:U123", status="completed") is False
