from __future__ import annotations

from datetime import datetime

from app.services import scheduler


class _NoopLease:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def assert_owned(self) -> None:
        return None


def test_scheduler_runs_one_job_per_account(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr("app.api.routes.ai._load_settings", lambda: {
        "enabled": True,
        "morning_time": "09:30",
        "midday_time": "12:30",
        "night_time": "20:00",
    })
    monkeypatch.setattr(scheduler, "job_already_completed", lambda *args, **kwargs: False)
    monkeypatch.setattr(scheduler, "try_acquire_job", lambda *args, **kwargs: True)
    monkeypatch.setattr(scheduler, "complete_job", lambda *args, **kwargs: True)
    monkeypatch.setattr(scheduler, "SchedulerLeaseHeartbeat", lambda *args, **kwargs: _NoopLease())

    def fake_run_scheduled_analysis(**kwargs):
        calls.append(kwargs["authorized_account_id"])
        return {"account_id": kwargs["authorized_account_id"]}

    monkeypatch.setattr(scheduler, "run_scheduled_analysis", fake_run_scheduled_analysis)

    class _Account:
        def __init__(self, account_id: str):
            self.id = account_id

    class _Adapter:
        def get_accounts(self):
            return [_Account("MOCK-001"), _Account("MOCK-002")]

    monkeypatch.setattr(scheduler, "get_broker_adapter", lambda: _Adapter())
    monkeypatch.setattr("app.core.config.settings.ibkr_account_id", None)

    scheduler._run_scheduler_sync(datetime(2026, 7, 10, 9, 35, tzinfo=scheduler._market_timezone()))

    assert calls == ["MOCK-001", "MOCK-002"]


def test_scheduler_slot_includes_account_id(monkeypatch):
    acquired: list[tuple[str, str]] = []

    monkeypatch.setattr("app.api.routes.ai._load_settings", lambda: {
        "enabled": True,
        "morning_time": "09:30",
        "midday_time": "12:30",
        "night_time": "20:00",
    })
    monkeypatch.setattr(scheduler, "job_already_completed", lambda *args, **kwargs: False)

    def fake_try_acquire(job_name, account_id, business_date, slot):
        acquired.append((account_id, slot))
        return True

    monkeypatch.setattr(scheduler, "try_acquire_job", fake_try_acquire)
    monkeypatch.setattr(scheduler, "complete_job", lambda *args, **kwargs: True)
    monkeypatch.setattr(scheduler, "SchedulerLeaseHeartbeat", lambda *args, **kwargs: _NoopLease())
    monkeypatch.setattr(scheduler, "run_scheduled_analysis", lambda **kwargs: {"ok": True})

    class _Account:
        def __init__(self, account_id: str):
            self.id = account_id

    class _Adapter:
        def get_accounts(self):
            return [_Account("MOCK-001")]

    monkeypatch.setattr(scheduler, "get_broker_adapter", lambda: _Adapter())
    monkeypatch.setattr("app.core.config.settings.ibkr_account_id", None)

    scheduler._run_scheduler_sync(datetime(2026, 7, 10, 9, 35, tzinfo=scheduler._market_timezone()))

    assert acquired == [("MOCK-001", "morning:MOCK-001")]
