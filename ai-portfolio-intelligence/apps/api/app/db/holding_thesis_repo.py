from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.sql_dialect import json_cast
from app.db.state_store import get_state_store, postgres_available

NAMESPACE = "holding_theses"


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(sql_text("SELECT 1 FROM holding_theses LIMIT 1"))
            session.execute(sql_text("SELECT 1 FROM holding_thesis_versions LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _norm_key(instrument_key: str) -> str:
    return instrument_key.upper()


def _record_key(account_id: str, instrument_key: str) -> str:
    return f"{account_id}:{_norm_key(instrument_key)}"


def _read_index() -> dict[str, Any]:
    payload = get_state_store().read_json(NAMESPACE, "index", default={})
    return payload if isinstance(payload, dict) else {}


def _write_index(index: dict[str, Any]) -> None:
    get_state_store().write_json(NAMESPACE, "index", index)


def get_thesis(account_id: str, instrument_key: str) -> dict[str, Any] | None:
    key = _record_key(account_id, instrument_key)
    if settings.persistence_backend == "postgres":
        available = _table_available()
        require_postgres_read("holding thesis read", table_available=available)
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                sql_text(
                    """
                    SELECT account_id, instrument_key, current_version, updated_at, payload_json
                    FROM holding_theses
                    WHERE account_id = :account_id AND UPPER(instrument_key) = :instrument_key
                    LIMIT 1
                    """
                ),
                {"account_id": account_id, "instrument_key": _norm_key(instrument_key)},
            ).mappings().first()
        if row is None:
            return None
        payload = dict(row["payload_json"] or {})
        payload.setdefault("account_id", row["account_id"])
        payload.setdefault("instrument_key", row["instrument_key"])
        payload.setdefault("version", int(row["current_version"]))
        if row["updated_at"] is not None:
            payload.setdefault("updated_at", row["updated_at"].isoformat())
        return payload

    index = _read_index()
    record = index.get(key)
    return dict(record) if isinstance(record, dict) else None


def list_thesis_versions(account_id: str, instrument_key: str) -> list[dict[str, Any]]:
    if settings.persistence_backend == "postgres":
        available = _table_available()
        require_postgres_read("holding thesis versions read", table_available=available)
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                sql_text(
                    """
                    SELECT account_id, instrument_key, version, thesis_text, author, created_at, payload_json
                    FROM holding_thesis_versions
                    WHERE account_id = :account_id AND UPPER(instrument_key) = :instrument_key
                    ORDER BY version ASC
                    """
                ),
                {"account_id": account_id, "instrument_key": _norm_key(instrument_key)},
            ).mappings().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = {
                "account_id": row["account_id"],
                "instrument_key": row["instrument_key"],
                "version": int(row["version"]),
                "thesis_text": row["thesis_text"],
                "author": row["author"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "payload": dict(row["payload_json"] or {}),
            }
            out.append(item)
        return out

    index = _read_index()
    record = index.get(_record_key(account_id, instrument_key))
    if not isinstance(record, dict):
        return []
    versions = record.get("versions") or []
    return [dict(item) for item in versions if isinstance(item, dict)]


def put_thesis(
    account_id: str,
    instrument_key: str,
    *,
    text: str,
    author: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("holding thesis write", table_available=_table_available())
        import json

        from sqlalchemy.exc import IntegrityError

        from app.db.session import SessionLocal

        max_attempts = 5
        last_error: Exception | None = None
        for _attempt in range(max_attempts):
            try:
                with SessionLocal() as session:
                    locked = session.execute(
                        sql_text(
                            """
                            SELECT current_version
                            FROM holding_theses
                            WHERE account_id = :account_id AND UPPER(instrument_key) = :instrument_key
                            FOR UPDATE
                            """
                        ),
                        {"account_id": account_id, "instrument_key": _norm_key(instrument_key)},
                    ).mappings().first()
                    version = int(locked["current_version"] if locked else 0) + 1
                    payload = {
                        "account_id": account_id,
                        "instrument_key": instrument_key,
                        "text": text,
                        "summary": text[:240],
                        "author": author,
                        "version": version,
                        "updated_at": now.isoformat(),
                        "metadata": metadata or {},
                        "methodology_status": "experimental",
                    }
                    session.execute(
                        sql_text(
                            f"""
                            INSERT INTO holding_theses (
                                account_id, instrument_key, current_version, updated_at, payload_json
                            ) VALUES (
                                :account_id, :instrument_key, :current_version, :updated_at, {json_cast("payload_json")}
                            )
                            ON CONFLICT (account_id, instrument_key)
                            DO UPDATE SET
                                current_version = EXCLUDED.current_version,
                                updated_at = EXCLUDED.updated_at,
                                payload_json = EXCLUDED.payload_json
                            """
                        ),
                        {
                            "account_id": account_id,
                            "instrument_key": instrument_key,
                            "current_version": version,
                            "updated_at": now,
                            "payload_json": json.dumps(payload),
                        },
                    )
                    session.execute(
                        sql_text(
                            f"""
                            INSERT INTO holding_thesis_versions (
                                account_id, instrument_key, version, thesis_text, author, created_at, payload_json
                            ) VALUES (
                                :account_id, :instrument_key, :version, :thesis_text, :author, :created_at,
                                {json_cast("payload_json")}
                            )
                            """
                        ),
                        {
                            "account_id": account_id,
                            "instrument_key": instrument_key,
                            "version": version,
                            "thesis_text": text,
                            "author": author,
                            "created_at": now,
                            "payload_json": json.dumps(payload),
                        },
                    )
                    session.commit()
                return payload
            except IntegrityError as exc:
                # First-insert race: concurrent writers both saw no row to FOR UPDATE.
                # Fail closed after retries — never silently drop a version.
                last_error = exc
                continue
        raise RuntimeError(
            "Holding thesis version allocation failed under concurrency; refusing silent version loss."
        ) from last_error

    existing = get_thesis(account_id, instrument_key) or {}
    version = int(existing.get("version") or 0) + 1
    payload = {
        "account_id": account_id,
        "instrument_key": instrument_key,
        "text": text,
        "summary": text[:240],
        "author": author,
        "version": version,
        "updated_at": now.isoformat(),
        "metadata": metadata or {},
        "methodology_status": "experimental",
    }
    version_row = {
        "account_id": account_id,
        "instrument_key": instrument_key,
        "version": version,
        "thesis_text": text,
        "author": author,
        "created_at": now.isoformat(),
        "payload": dict(payload),
    }
    index = _read_index()
    key = _record_key(account_id, instrument_key)
    prior = index.get(key) if isinstance(index.get(key), dict) else {}
    versions = list(prior.get("versions") or []) if isinstance(prior, dict) else []
    versions.append(version_row)
    stored: dict[str, Any] = dict(payload)
    stored["versions"] = versions
    index[key] = stored
    _write_index(index)
    return payload
