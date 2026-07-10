from __future__ import annotations

import json
import os
import socket
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.db.state_store import get_state_store


from app.api.account_deps import SCHEDULER_ALL_ACCOUNTS


def _job_account_id(account_id: str | None) -> str:
    return account_id or SCHEDULER_ALL_ACCOUNTS


def _json_idempotency_key(job_name: str, account_id: str | None, business_date: date, slot: str) -> str:
    account = _job_account_id(account_id)
    return f"{job_name}:{account}:{business_date.isoformat()}:{slot}"


_active_claims: dict[str, tuple[str, int]] = {}


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
            normalized_account = _job_account_id(account_id)
            store.write_json(
                "scheduled_jobs",
                key,
                {
                    "job_name": job_name,
                    "account_id": normalized_account,
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
                    "fencing_token": 1,
                },
            )
            _active_claims[key] = (_worker_id(), 1)
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
                "fencing_token": int(existing.get("fencing_token", 0)) + 1,
            },
        )
        _active_claims[key] = (_worker_id(), int(existing.get("fencing_token", 0)) + 1)
        return True

    from app.db.session import SessionLocal
    from app.models.professional_state import ScheduledJob

    normalized_account = _job_account_id(account_id)
    worker = _worker_id()
    claim_key = _json_idempotency_key(job_name, account_id, business_date, slot)

    with SessionLocal() as session:
        row = (
            session.query(ScheduledJob)
            .filter(
                ScheduledJob.job_name == job_name,
                ScheduledJob.account_id == normalized_account,
                ScheduledJob.business_date == business_date,
                ScheduledJob.slot == slot,
            )
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if row is None:
            try:
                session.add(
                    ScheduledJob(
                        job_name=job_name,
                        account_id=normalized_account,
                        business_date=business_date,
                        slot=slot,
                        status="running",
                        attempt_count=1,
                        max_attempts=settings.scheduler_max_attempts,
                        leased_until=_lease_expiry(now),
                        worker_id=worker,
                        heartbeat_at=now,
                        created_at=now,
                        fencing_token=1,
                    )
                )
                session.commit()
                _active_claims[claim_key] = (worker, 1)
                return True
            except IntegrityError:
                session.rollback()
                row = (
                    session.query(ScheduledJob)
                    .filter(
                        ScheduledJob.job_name == job_name,
                        ScheduledJob.account_id == normalized_account,
                        ScheduledJob.business_date == business_date,
                        ScheduledJob.slot == slot,
                    )
                    .with_for_update()
                    .one_or_none()
                )
                if row is None:
                    return False

        if row.status == "completed":
            session.rollback()
            return False
        if row.status == "running" and row.leased_until and row.leased_until > now:
            session.rollback()
            return False
        if row.status == "failed":
            if row.attempt_count >= row.max_attempts:
                session.rollback()
                return False
            if row.next_retry_at and row.next_retry_at > now:
                session.rollback()
                return False

        row.status = "running"
        row.attempt_count = (row.attempt_count or 0) + 1
        row.max_attempts = settings.scheduler_max_attempts
        row.leased_until = _lease_expiry(now)
        row.worker_id = worker
        row.heartbeat_at = now
        row.error_message = None
        row.completed_at = None
        row.fencing_token = (row.fencing_token or 0) + 1
        session.commit()
        _active_claims[claim_key] = (worker, row.fencing_token)
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
    normalized_account = _job_account_id(account_id)
    claim_key = _json_idempotency_key(job_name, account_id, business_date, slot)
    worker = _worker_id()
    expected_claim = _active_claims.get(claim_key)
    if settings.persistence_backend != "postgres":
        store = get_state_store()
        key = claim_key
        existing = store.read_json("scheduled_jobs", key, default={}) or {}
        if existing.get("worker_id") and existing.get("worker_id") != worker:
            return
        if expected_claim and int(existing.get("fencing_token", 0)) != expected_claim[1]:
            return
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
                "account_id": normalized_account,
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
        _active_claims.pop(claim_key, None)
        return

    from app.db.session import SessionLocal

    fencing_token = expected_claim[1] if expected_claim else None
    payload_text = json.dumps(payload) if payload is not None else None
    next_retry_sql = None
    with SessionLocal() as session:
        if status == "failed":
            row = session.execute(
                text(
                    """
                    SELECT attempt_count, max_attempts
                    FROM scheduled_jobs
                    WHERE job_name = :job_name
                      AND account_id = :account_id
                      AND business_date = :business_date
                      AND slot = :slot
                    """
                ),
                {
                    "job_name": job_name,
                    "account_id": normalized_account,
                    "business_date": business_date,
                    "slot": slot,
                },
            ).mappings().first()
            if row and row["attempt_count"] < row["max_attempts"]:
                next_retry_sql = _retry_at(int(row["attempt_count"]), now)

        result = session.execute(
            text(
                """
                UPDATE scheduled_jobs
                SET status = :status,
                    payload_json = :payload_json,
                    error_message = :error_message,
                    completed_at = :completed_at,
                    leased_until = NULL,
                    next_retry_at = :next_retry_at
                WHERE job_name = :job_name
                  AND account_id = :account_id
                  AND business_date = :business_date
                  AND slot = :slot
                  AND status = 'running'
                  AND worker_id = :worker_id
                  AND fencing_token = :fencing_token
                RETURNING id
                """
            ),
            {
                "status": status,
                "payload_json": payload_text,
                "error_message": error_message,
                "completed_at": now,
                "next_retry_at": next_retry_sql,
                "job_name": job_name,
                "account_id": normalized_account,
                "business_date": business_date,
                "slot": slot,
                "worker_id": worker,
                "fencing_token": fencing_token if fencing_token is not None else -1,
            },
        ).first()
        if result is None:
            session.rollback()
            return
        session.commit()
        _active_claims.pop(claim_key, None)


def renew_job_lease(
    job_name: str,
    account_id: str | None,
    business_date: date,
    slot: str,
) -> bool:
    claim_key = _json_idempotency_key(job_name, account_id, business_date, slot)
    expected_claim = _active_claims.get(claim_key)
    if expected_claim is None:
        return False
    worker, fencing_token = expected_claim
    now = _utc_now()
    normalized_account = _job_account_id(account_id)

    if settings.persistence_backend != "postgres":
        store = get_state_store()
        existing = store.read_json("scheduled_jobs", claim_key, default={}) or {}
        if existing.get("worker_id") != worker or int(existing.get("fencing_token", 0)) != fencing_token:
            return False
        store.write_json(
            "scheduled_jobs",
            claim_key,
            {
                **existing,
                "leased_until": _lease_expiry(now).isoformat(),
                "heartbeat_at": now.isoformat(),
            },
        )
        return True

    from sqlalchemy import text

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        result = session.execute(
            text(
                """
                UPDATE scheduled_jobs
                SET leased_until = :leased_until,
                    heartbeat_at = :heartbeat_at
                WHERE job_name = :job_name
                  AND account_id = :account_id
                  AND business_date = :business_date
                  AND slot = :slot
                  AND status = 'running'
                  AND worker_id = :worker_id
                  AND fencing_token = :fencing_token
                RETURNING id
                """
            ),
            {
                "leased_until": _lease_expiry(now),
                "heartbeat_at": now,
                "job_name": job_name,
                "account_id": normalized_account,
                "business_date": business_date,
                "slot": slot,
                "worker_id": worker,
                "fencing_token": fencing_token,
            },
        ).first()
        if result is None:
            session.rollback()
            return False
        session.commit()
        return True


def job_already_completed(
    job_name: str,
    account_id: str | None,
    business_date: date,
    slot: str,
) -> bool:
    normalized_account = _job_account_id(account_id)
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
                ScheduledJob.account_id == normalized_account,
                ScheduledJob.business_date == business_date,
                ScheduledJob.slot == slot,
                ScheduledJob.status == "completed",
            )
            .one_or_none()
        )
        return row is not None
