from __future__ import annotations

import hashlib
import json
import os
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

_FILE_LOCK = Lock()


class StateStoreError(RuntimeError):
    pass


class StateCorruptionError(StateStoreError):
    pass


def _data_dir() -> str:
    from app.core.desktop_bootstrap import state_data_dir

    return str(state_data_dir())


def _safe_component(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    def __init__(self, root: Path | str | None = None) -> None:
        self._root_override = Path(root).resolve() if root is not None else None

    def _root(self) -> Path:
        if self._root_override is not None:
            return self._root_override
        return Path(_data_dir()).resolve()

    def _path(self, namespace: str, record_key: str) -> Path:
        root = self._root()
        path = (root / _safe_component(namespace) / f"{_safe_component(record_key)}.json").resolve()
        if root != path and root not in path.parents:
            raise StateStoreError("Resolved state path escaped the state root")
        return path

    def read_json(self, namespace: str, record_key: str, default: Any = None) -> Any:
        path = self._path(namespace, record_key)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            quarantine = path.with_suffix(f".corrupt-{stamp}.json")
            path.replace(quarantine)
            raise StateCorruptionError(
                f"Corrupted state was quarantined: {quarantine.name}"
            ) from exc
        except OSError as exc:
            raise StateStoreError(
                f"Unable to read state record {namespace}/{record_key}"
            ) from exc

    def write_json(self, namespace: str, record_key: str, payload: Any) -> None:
        path = self._path(namespace, record_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _FILE_LOCK:
            fd, temporary_path = tempfile.mkstemp(
                prefix="state_",
                suffix=".tmp",
                dir=str(path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
                directory_fd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)

    def delete(self, namespace: str, record_key: str) -> None:
        path = self._path(namespace, record_key)
        if path.exists():
            path.unlink()


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
            except json.JSONDecodeError as exc:
                raise StateCorruptionError(
                    f"Corrupted postgres state for {namespace}/{record_key}"
                ) from exc

    def write_json(self, namespace: str, record_key: str, payload: Any) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

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
