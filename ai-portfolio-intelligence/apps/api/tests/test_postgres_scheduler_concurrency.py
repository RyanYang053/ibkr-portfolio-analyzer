from datetime import date

import os
import pytest

from app.db.scheduler_store import complete_job, try_acquire_job


@pytest.mark.skipif(
    os.getenv("PERSISTENCE_BACKEND") != "postgres" or not os.getenv("DATABASE_URL"),
    reason="Postgres scheduler concurrency requires DATABASE_URL and PERSISTENCE_BACKEND=postgres",
)
def test_postgres_scheduler_concurrent_claim_only_one_worker_wins():
    business_date = date(2026, 7, 11)
    first = try_acquire_job("scheduled_analysis", "U123", business_date, "morning")
    second = try_acquire_job("scheduled_analysis", "U123", business_date, "morning")
    assert first is True
    assert second is False
    complete_job("scheduled_analysis", "U123", business_date, "morning", status="completed")
    third = try_acquire_job("scheduled_analysis", "U123", business_date, "morning")
    assert third is False
