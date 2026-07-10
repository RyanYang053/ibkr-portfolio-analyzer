from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProfessionalStateRecord(Base):
    __tablename__ = "professional_state_records"
    __table_args__ = (
        UniqueConstraint("namespace", "record_key", name="uq_professional_state_namespace_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        UniqueConstraint(
            "job_name",
            "account_id",
            "business_date",
            "slot",
            name="uq_scheduled_jobs_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(64))
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    payload_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(64))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
