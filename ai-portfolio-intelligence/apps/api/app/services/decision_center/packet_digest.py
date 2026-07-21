"""Packet digest helpers for immutability / reproducibility."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def packet_digest(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "packet_sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
