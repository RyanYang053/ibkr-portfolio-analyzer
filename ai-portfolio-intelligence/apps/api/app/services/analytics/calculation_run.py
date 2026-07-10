from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

METHODOLOGY_VERSION = "2026.07.2"


class CalculationRun(BaseModel):
    calculation_run_id: str
    run_type: str
    account_id: str
    methodology_version: str = METHODOLOGY_VERSION
    input_snapshot_ids: list[str] = Field(default_factory=list)
    transaction_batch_ids: list[str] = Field(default_factory=list)
    fx_observation_ids: list[str] = Field(default_factory=list)
    market_data_observation_ids: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    coverage: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def create_calculation_run(
    *,
    run_type: str,
    account_id: str,
    input_snapshot_ids: list[str] | None = None,
    transaction_batch_ids: list[str] | None = None,
    fx_observation_ids: list[str] | None = None,
    market_data_observation_ids: list[str] | None = None,
    exclusions: list[str] | None = None,
    coverage: dict[str, str] | None = None,
    methodology_version: str = METHODOLOGY_VERSION,
) -> CalculationRun:
    run = CalculationRun(
        calculation_run_id=str(uuid.uuid4()),
        run_type=run_type,
        account_id=account_id,
        methodology_version=methodology_version,
        input_snapshot_ids=input_snapshot_ids or [],
        transaction_batch_ids=transaction_batch_ids or [],
        fx_observation_ids=fx_observation_ids or [],
        market_data_observation_ids=market_data_observation_ids or [],
        exclusions=exclusions or [],
        coverage=coverage or {},
    )
    from app.db.calculation_run_repo import insert_calculation_run

    insert_calculation_run(run.calculation_run_id, run.run_type, run.account_id, run.model_dump(mode="json"))
    return run


def load_calculation_run(account_id: str, run_id: str) -> CalculationRun | None:
    from app.db.calculation_run_repo import read_calculation_run

    payload = read_calculation_run(account_id, run_id)
    if not payload:
        return None
    return CalculationRun(**payload)


def run_metadata_dict(run: CalculationRun) -> dict[str, Any]:
    return {
        "calculation_run_id": run.calculation_run_id,
        "methodology_version": run.methodology_version,
        "input_snapshot_ids": run.input_snapshot_ids,
        "transaction_batch_ids": run.transaction_batch_ids,
        "fx_observation_ids": run.fx_observation_ids,
        "market_data_observation_ids": run.market_data_observation_ids,
        "exclusions": run.exclusions,
        "coverage": run.coverage,
        "created_at": run.created_at.isoformat(),
    }
