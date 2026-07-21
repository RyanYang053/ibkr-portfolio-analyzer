"""Trade journal API (plan §10 / §19)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import Principal, get_current_principal
from app.db.journal_repo import get_journal_entry, list_journal_entries, save_journal_entry
from app.schemas.journal import (
    JournalEntry,
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalReview,
    ReviewInterval,
)
from app.services.journal.analytics import compute_process_analytics

router = APIRouter(
    prefix="/journal",
    tags=["journal"],
    dependencies=[Depends(get_current_principal)],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require(entry_id: str) -> JournalEntry:
    entry = get_journal_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown journal entry: {entry_id}")
    return entry


@router.get("")
def list_entries(account_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    entries = list_journal_entries(account_id)
    return {
        "account_id": account_id,
        "count": len(entries),
        "entries": [e.model_dump(mode="json") for e in entries],
    }


@router.post("")
def create_entry(body: JournalEntryCreate, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    symbol = (body.symbol or body.instrument_id.split(":", 1)[0]).strip().upper()
    entry = JournalEntry(
        entry_id=f"je_{uuid4().hex[:16]}",
        account_id=body.account_id,
        instrument_id=body.instrument_id,
        symbol=symbol,
        trade_plan_id=body.trade_plan_id,
        decision_packet_id=body.decision_packet_id,
        thesis_version_id=body.thesis_version_id,
        entry_thesis=body.entry_thesis,
        expected_catalyst=body.expected_catalyst,
        expected_holding_period=body.expected_holding_period,
        strategy=body.strategy,
        confidence=body.confidence,
        entry_price=body.entry_price,
        position_size=body.position_size,
        planned_maximum_loss=body.planned_maximum_loss,
        created_at=_now(),
    )
    save_journal_entry(entry)
    return entry.model_dump(mode="json")


@router.get("/analytics")
def journal_analytics(account_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    entries = list_journal_entries(account_id)
    return compute_process_analytics(entries)


@router.get("/{entry_id}")
def get_entry(entry_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return _require(entry_id).model_dump(mode="json")


@router.patch("/{entry_id}")
def update_entry(
    entry_id: str,
    body: JournalEntryUpdate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    entry = _require(entry_id)
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)
    if entry.exit_price is not None and entry.closed_at is None:
        entry.closed_at = _now()
    save_journal_entry(entry)
    return entry.model_dump(mode="json")


class ReviewRequest(BaseModel):
    interval: ReviewInterval = ReviewInterval.CUSTOM
    note: str = ""
    rule_adherence: bool | None = None
    lessons: list[str] = []


@router.post("/{entry_id}/review")
def add_review(
    entry_id: str,
    body: ReviewRequest,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    entry = _require(entry_id)
    review = JournalReview(
        review_id=f"jr_{uuid4().hex[:12]}",
        interval=body.interval,
        note=body.note,
        rule_adherence=body.rule_adherence,
        lessons=body.lessons,
        created_at=_now(),
    )
    entry.reviews.append(review)
    save_journal_entry(entry)
    return entry.model_dump(mode="json")
