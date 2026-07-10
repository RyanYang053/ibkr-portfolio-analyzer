from __future__ import annotations

from datetime import date

import pytest

from app.services import scheduler
from app.services.system_actor import SCHEDULER_ACTOR


class _NoopLease:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def assert_owned(self) -> None:
        return None


def test_scheduled_analysis_uses_system_actor_not_fake_principal(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(scheduler, "job_already_completed", lambda *args, **kwargs: False)
    monkeypatch.setattr(scheduler, "SchedulerLeaseHeartbeat", lambda *args, **kwargs: _NoopLease())

    def fake_run_scheduled_analysis(**kwargs):
        captured.update(kwargs)
        return {"period": kwargs["period"], "account_id": kwargs["authorized_account_id"]}

    monkeypatch.setattr(scheduler, "run_scheduled_analysis", fake_run_scheduled_analysis)
    monkeypatch.setattr(
        scheduler,
        "complete_job",
        lambda *args, **kwargs: True,
    )

    class _Account:
        def __init__(self, account_id: str):
            self.id = account_id

    class _Adapter:
        def get_accounts(self):
            return [_Account("MOCK-001"), _Account("MOCK-002")]

    scheduler._run_scheduled_analysis_for_accounts(
        adapter=_Adapter(),
        period="morning",
        business_date=date(2026, 7, 10),
        account_ids=["MOCK-001", "MOCK-002"],
    )

    assert captured["actor"] == SCHEDULER_ACTOR
    assert captured["authorized_account_id"] == "MOCK-002"
    assert "principal" not in captured


def test_scheduler_resolves_configured_account_only(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ibkr_account_id", "U999")

    class _Account:
        def __init__(self, account_id: str):
            self.id = account_id

    class _Adapter:
        def get_accounts(self):
            return [_Account("MOCK-001"), _Account("MOCK-002")]

    account_ids = scheduler._scheduled_analysis_account_ids(_Adapter())
    assert account_ids == ["U999"]
