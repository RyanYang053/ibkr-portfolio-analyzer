from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.db.state_store import get_state_store


def _json_idempotency_key(job_name: str, account_id: str | None, business_date: date, slot: str) -> str:
    account = account_id or "__all__"
    return f"{job_name}:{account}:{business_date.isoformat()}:{slot}"


def try_acquire_job(
    job_name: str,
    account_id: str | None,
    business_date: date,
    slot: str,
) -> bool:
    if settings.persistence_backend != "postgres":
        store = get_state_store()
        key = _json_idempotency_key(job_name, account_id, business_date, slot)
        existing = store.read_json("scheduled_jobs", key, default=None)
        if existing is not None:
            return False
        store.write_json(
            "scheduled_jobs",
            key,
            {
                "job_name": job_name,
                "account_id": account_id,
                "business_date": business_date.isoformat(),
                "slot": slot,
                "status": "running",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True

    from app.db.session import SessionLocal
    from app.models.professional_state import ScheduledJob

    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        try:
            row = ScheduledJob(
                job_name=job_name,
                account_id=account_id,
                business_date=business_date,
                slot=slot,
                status="running",
                created_at=now,
            )
            session.add(row)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False
        except SQLAlchemyError:
            session.rollback()
            return False


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
    if settings.persistence_backend != "postgres":
        store = get_state_store()
        key = _json_idempotency_key(job_name, account_id, business_date, slot)
        store.write_json(
            "scheduled_jobs",
            key,
            {
                "job_name": job_name,
                "account_id": account_id,
                "business_date": business_date.isoformat(),
                "slot": slot,
                "status": status,
                "payload": payload,
                "error_message": error_message,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return

    from app.db.session import SessionLocal
    from app.models.professional_state import ScheduledJob

    now = datetime.now(timezone.utc)
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
