"""Research notes persistence (plan §8.5 / §17)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import settings
from app.db.sql_dialect import json_cast
from app.schemas.research_note import ResearchNote

_NS = "research_notes"


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def _load(row) -> dict:
    return row if isinstance(row, dict) else json.loads(row)


def save_note(note: ResearchNote) -> ResearchNote:
    now = datetime.now(timezone.utc)
    if note.created_at is None:
        note.created_at = now
    note.updated_at = now
    payload = note.model_dump(mode="json")
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            existing = session.execute(
                text("SELECT payload_json FROM research_notes WHERE note_id = :nid"), {"nid": note.note_id}
            ).scalar()
            if existing is not None:
                note.version = int(_load(existing).get("version", 1)) + 1
                payload = note.model_dump(mode="json")
            session.execute(
                text(
                    f"""
                    INSERT INTO research_notes (note_id, account_id, instrument_id, note_type, payload_json, created_at, updated_at)
                    VALUES (:nid, :account_id, :instrument_id, :note_type, {json_cast("payload_json")}, :created_at, :updated_at)
                    ON CONFLICT(note_id) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                    """
                ),
                {"nid": note.note_id, "account_id": note.account_id, "instrument_id": note.instrument_id,
                 "note_type": note.note_type.value, "payload_json": json.dumps(payload),
                 "created_at": note.created_at, "updated_at": now},
            )
            session.commit()
        return note
    from app.db.state_store import get_state_store

    store = get_state_store()
    prev = store.read_json(_NS, note.note_id, default=None)
    if prev:
        note.version = int(prev.get("version", 1)) + 1
        payload = note.model_dump(mode="json")
    store.write_json(_NS, note.note_id, payload)
    idx = store.read_json(_NS, f"index:{note.account_id}", default={"ids": []}) or {"ids": []}
    ids = list(idx.get("ids") or [])
    if note.note_id not in ids:
        ids.insert(0, note.note_id)
        store.write_json(_NS, f"index:{note.account_id}", {"ids": ids})
    return note


def get_note(note_id: str) -> ResearchNote | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM research_notes WHERE note_id = :nid"), {"nid": note_id}
            ).scalar()
        return ResearchNote.model_validate(_load(row)) if row is not None else None
    from app.db.state_store import get_state_store

    payload = get_state_store().read_json(_NS, note_id, default=None)
    return ResearchNote.model_validate(payload) if payload else None


def list_notes(account_id: str, *, instrument_id: str | None = None, limit: int = 200) -> list[ResearchNote]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        clause = "WHERE account_id = :a"
        params = {"a": account_id, "limit": limit}
        if instrument_id:
            clause += " AND instrument_id = :iid"
            params["iid"] = instrument_id
        with SessionLocal() as session:
            rows = session.execute(
                text(f"SELECT payload_json FROM research_notes {clause} ORDER BY updated_at DESC LIMIT :limit"),
                params,
            ).scalars().all()
        return [ResearchNote.model_validate(_load(r)) for r in rows]
    from app.db.state_store import get_state_store

    store = get_state_store()
    idx = store.read_json(_NS, f"index:{account_id}", default={"ids": []}) or {"ids": []}
    out = []
    for nid in (idx.get("ids") or [])[:limit]:
        payload = store.read_json(_NS, str(nid), default=None)
        if not payload:
            continue
        note = ResearchNote.model_validate(payload)
        if instrument_id and note.instrument_id != instrument_id:
            continue
        out.append(note)
    return out
