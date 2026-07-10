from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

_FILE_LOCK = Lock()


def _data_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "state",
    )


class StateStore(ABC):
    @abstractmethod
    def read_json(self, namespace: str, record_key: str, default: Any = None) -> Any:
        raise NotImplementedError

    @abstractmethod
    def write_json(self, namespace: str, record_key: str, payload: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, namespace: str, record_key: str) -> None:
        raise NotImplementedError


class JsonStateStore(StateStore):
    def _path(self, namespace: str, record_key: str) -> str:
        safe_ns = namespace.replace("/", "_")
        safe_key = record_key.replace("/", "_").replace("..", "_")
        return os.path.join(_data_dir(), safe_ns, f"{safe_key}.json")

    def read_json(self, namespace: str, record_key: str, default: Any = None) -> Any:
        path = self._path(namespace, record_key)
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return default

    def write_json(self, namespace: str, record_key: str, payload: Any) -> None:
        path = self._path(namespace, record_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _FILE_LOCK:
            fd, temporary_path = tempfile.mkstemp(prefix="state_", suffix=".tmp", dir=os.path.dirname(path))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)

    def delete(self, namespace: str, record_key: str) -> None:
        path = self._path(namespace, record_key)
        if os.path.exists(path):
            os.unlink(path)


class PostgresStateStore(StateStore):
    def read_json(self, namespace: str, record_key: str, default: Any = None) -> Any:
        from app.db.session import SessionLocal
        from app.models.professional_state import ProfessionalStateRecord

        with SessionLocal() as session:
            row = (
                session.query(ProfessionalStateRecord)
                .filter(
                    ProfessionalStateRecord.namespace == namespace,
                    ProfessionalStateRecord.record_key == record_key,
                )
                .one_or_none()
            )
            if row is None:
                return default
            try:
                return json.loads(row.payload_json)
            except json.JSONDecodeError:
                return default

    def write_json(self, namespace: str, record_key: str, payload: Any) -> None:
        from app.db.session import SessionLocal
        from app.models.professional_state import ProfessionalStateRecord

        now = datetime.now(timezone.utc)
        payload_text = json.dumps(payload)
        with SessionLocal() as session:
            stmt = pg_insert(ProfessionalStateRecord).values(
                namespace=namespace,
                record_key=record_key,
                payload_json=payload_text,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["namespace", "record_key"],
                set_={"payload_json": payload_text, "updated_at": now},
            )
            session.execute(stmt)
            session.commit()

    def delete(self, namespace: str, record_key: str) -> None:
        from app.db.session import SessionLocal
        from app.models.professional_state import ProfessionalStateRecord

        with SessionLocal() as session:
            session.query(ProfessionalStateRecord).filter(
                ProfessionalStateRecord.namespace == namespace,
                ProfessionalStateRecord.record_key == record_key,
            ).delete()
            session.commit()


def get_state_store() -> StateStore:
    if settings.persistence_backend == "postgres":
        return PostgresStateStore()
    return JsonStateStore()


def postgres_available() -> bool:
    if settings.persistence_backend != "postgres":
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.connection()
        return True
    except SQLAlchemyError:
        return False
