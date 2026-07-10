from __future__ import annotations

import json
import os
import socket
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.db.state_store import get_state_store


def _json_idempotency_key(job_name: str, account_id: str | None, business_date: date, slot: str) -> str:
    account = account_id or "__all__"
    return f"{job_name}:{account}:{business_date.isoformat()}:{slot}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _lease_expiry(now: datetime) -> datetime:
    return now + timedelta(minutes=settings.scheduler_lease_minutes)


def _retry_at(attempt_count: int, now: datetime) -> datetime:
    delay_minutes = 5 * (3 ** max(0, attempt_count - 1))
    return now + timedelta(minutes=delay_minutes)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _can_acquire_existing(record: dict[str, Any], now: datetime) -> bool:
    status = record.get("status")
    max_attempts = int(record.get("max_attempts", settings.scheduler_max_attempts))
    attempt_count = int(record.get("attempt_count", 0))

    if status == "completed":
        return False
    if status == "running":
        leased_until = _parse_timestamp(record.get("leased_until"))
        return leased_until is None or leased_until <= now
    if status == "failed":
        if attempt_count >= max_attempts:
            return False
        next_retry_at = _parse_timestamp(record.get("next_retry_at"))
        return next_retry_at is None or next_retry_at <= now
    return True


def try_acquire_job(
    job_name: str,
    account_id: str | None,
    business_date: date,
    slot: str,
) -> bool:
    now = _utc_now()
    if settings.persistence_backend != "postgres":
        store = get_state_store()
        key = _json_idempotency_key(job_name, account_id, business_date, slot)
        existing = store.read_json("scheduled_jobs", key, default=None)
        if existing is None:
            store.write_json(
                "scheduled_jobs",
                key,
                {
                    "job_name": job_name,
                    "account_id": account_id,
                    "business_date": business_date.isoformat(),
                    "slot": slot,
                    "status": "running",
                    "attempt_count": 1,
                    "max_attempts": settings.scheduler_max_attempts,
                    "leased_until": _lease_expiry(now).isoformat(),
                    "worker_id": _worker_id(),
                    "next_retry_at": None,
                    "heartbeat_at": now.isoformat(),
                    "created_at": now.isoformat(),
                },
            )
            return True
        if not _can_acquire_existing(existing, now):
            return False
        attempt_count = int(existing.get("attempt_count", 0)) + 1
        store.write_json(
            "scheduled_jobs",
            key,
            {
                **existing,
                "status": "running",
                "attempt_count": attempt_count,
                "max_attempts": settings.scheduler_max_attempts,
                "leased_until": _lease_expiry(now).isoformat(),
                "worker_id": _worker_id(),
                "heartbeat_at": now.isoformat(),
                "error_message": None,
            },
        )
        return True

    from app.db.session import SessionLocal
    from app.models.professional_state import ScheduledJob

    with SessionLocal() as session:
        row = (
            session.query(ScheduledJob)
            .filter(
                ScheduledJob.job_name == job_name,
                ScheduledJob.account_id == account_id,
                ScheduledJob.business_date == business_date,
                ScheduledJob.slot == slot,
            )
            .one_or_none()
        )
        if row is None:
            try:
                session.add(
                    ScheduledJob(
                        job_name=job_name,
                        account_id=account_id,
                        business_date=business_date,
                        slot=slot,
                        status="running",
                        attempt_count=1,
                        max_attempts=settings.scheduler_max_attempts,
                        leased_until=_lease_expiry(now),
                        worker_id=_worker_id(),
                        heartbeat_at=now,
                        created_at=now,
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                row = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.job_name == job_name,
                        ScheduledJob.account_id == account_id,
                        ScheduledJob.business_date == business_date,
                        ScheduledJob.slot == slot,
                    )
                    .one_or_none()
                )
                if row is None:
                    return False

        if row.status == "completed":
            return False
        if row.status == "running" and row.leased_until and row.leased_until > now:
            return False
        if row.status == "failed":
            if row.attempt_count >= row.max_attempts:
                return False
            if row.next_retry_at and row.next_retry_at > now:
                return False

        row.status = "running"
        row.attempt_count = (row.attempt_count or 0) + 1
        row.max_attempts = settings.scheduler_max_attempts
        row.leased_until = _lease_expiry(now)
        row.worker_id = _worker_id()
        row.heartbeat_at = now
        row.error_message = None
        row.completed_at = None
        session.commit()
        return True


def complete_job(
    job_name: str,
    account_id: str | None,
    business_date: date,
    slot: str,
    *,
    status: str = "completed",
    payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    now = _utc_now()
    if settings.persistence_backend != "postgres":
        store = get_state_store()
        key = _json_idempotency_key(job_name, account_id, business_date, slot)
        existing = store.read_json("scheduled_jobs", key, default={}) or {}
        next_retry_at = None
        if status == "failed":
            attempt_count = int(existing.get("attempt_count", 1))
            max_attempts = int(existing.get("max_attempts", settings.scheduler_max_attempts))
            if attempt_count < max_attempts:
                next_retry_at = _retry_at(attempt_count, now).isoformat()
        store.write_json(
            "scheduled_jobs",
            key,
            {
                **existing,
                "job_name": job_name,
                "account_id": account_id,
                "business_date": business_date.isoformat(),
                "slot": slot,
                "status": status,
                "payload": payload,
                "error_message": error_message,
                "completed_at": now.isoformat(),
                "leased_until": None,
                "next_retry_at": next_retry_at,
            },
        )
        return

    from app.db.session import SessionLocal
    from app.models.professional_state import ScheduledJob

    with SessionLocal() as session:
        row = (
            session.query(ScheduledJob)
            .filter(
                ScheduledJob.job_name == job_name,
                ScheduledJob.account_id == account_id,
                ScheduledJob.business_date == business_date,
                ScheduledJob.slot == slot,
            )
            .one_or_none()
        )
        if row is None:
            return
        row.status = status
        row.payload_json = json.dumps(payload) if payload is not None else None
        row.error_message = error_message
        row.completed_at = now
        row.leased_until = None
        if status == "failed" and row.attempt_count < row.max_attempts:
            row.next_retry_at = _retry_at(row.attempt_count, now)
        else:
            row.next_retry_at = None
        session.commit()


def job_already_completed(
    job_name: str,
    account_id: str | None,
    business_date: date,
    slot: str,
) -> bool:
    if settings.persistence_backend != "postgres":
        store = get_state_store()
        key = _json_idempotency_key(job_name, account_id, business_date, slot)
        record = store.read_json("scheduled_jobs", key, default=None)
        return isinstance(record, dict) and record.get("status") == "completed"

    from app.db.session import SessionLocal
    from app.models.professional_state import ScheduledJob

    with SessionLocal() as session:
        row = (
            session.query(ScheduledJob)
            .filter(
                ScheduledJob.job_name == job_name,
                ScheduledJob.account_id == account_id,
                ScheduledJob.business_date == business_date,
                ScheduledJob.slot == slot,
                ScheduledJob.status == "completed",
            )
            .one_or_none()
        )
        return row is not None
