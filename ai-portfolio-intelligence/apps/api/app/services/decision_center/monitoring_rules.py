from __future__ import annotations

from typing import Any

from app.db import decision_monitoring_repo


def list_monitoring_rules(account_id: str) -> list[dict[str, Any]]:
    return decision_monitoring_repo.list_rules(account_id)


def create_monitoring_rule(
    account_id: str,
    *,
    instrument_key: str | None,
    rule_type: str,
    threshold: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return decision_monitoring_repo.create_rule(
        account_id,
        instrument_key=instrument_key,
        rule_type=rule_type,
        threshold=threshold,
        note=note,
    )
