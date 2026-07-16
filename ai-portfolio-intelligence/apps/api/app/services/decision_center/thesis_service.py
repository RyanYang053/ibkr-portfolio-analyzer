from __future__ import annotations

from typing import Any

from app.db import holding_thesis_repo


def get_thesis(account_id: str, instrument_key: str) -> dict[str, Any] | None:
    return holding_thesis_repo.get_thesis(account_id, instrument_key)


def put_thesis(
    account_id: str,
    instrument_key: str,
    *,
    text: str,
    author: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return holding_thesis_repo.put_thesis(
        account_id,
        instrument_key,
        text=text,
        author=author,
        metadata=metadata,
    )
