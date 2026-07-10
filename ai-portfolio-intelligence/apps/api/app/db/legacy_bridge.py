from __future__ import annotations

import json
import os
from typing import Any

from app.db.state_store import get_state_store


def read_json_with_legacy(
    namespace: str,
    record_key: str,
    legacy_path: str | None,
    default: Any = None,
) -> Any:
    store = get_state_store()
    current = store.read_json(namespace, record_key, default=None)
    if current is not None:
        return current
    if legacy_path and os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            store.write_json(namespace, record_key, payload)
            return payload
        except Exception:
            return default
    return default


def write_json_state(namespace: str, record_key: str, payload: Any) -> None:
    get_state_store().write_json(namespace, record_key, payload)
