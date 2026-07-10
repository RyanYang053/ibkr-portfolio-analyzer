from __future__ import annotations

import threading
from datetime import date

from app.core.config import settings
from app.db.scheduler_store import renew_job_lease


class SchedulerLeaseHeartbeat:
    """Renew scheduler leases periodically while a long-running job executes."""

    def __init__(
        self,
        job_name: str,
        account_id: str | None,
        business_date: date,
        slot: str,
    ) -> None:
        self.job_name = job_name
        self.account_id = account_id
        self.business_date = business_date
        self.slot = slot
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _interval_seconds(self) -> float:
        lease_minutes = max(int(settings.scheduler_lease_minutes), 1)
        return max(lease_minutes * 60.0 / 3.0, 30.0)

    def _renew(self) -> None:
        renew_job_lease(self.job_name, self.account_id, self.business_date, self.slot)

    def __enter__(self) -> SchedulerLeaseHeartbeat:
        self._renew()

        def _loop() -> None:
            while not self._stop.wait(self._interval_seconds()):
                self._renew()

        self._thread = threading.Thread(target=_loop, daemon=True, name="scheduler-lease-heartbeat")
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
