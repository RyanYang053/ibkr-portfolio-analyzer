"""Remaining Section-17 tables (plan §17): risk/stress/catalysts/settings/reference.

Revision ID: 0046_remaining_section17
Revises: 0045_options_state
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0046_remaining_section17"
down_revision = "0045_options_state"
branch_labels = None
depends_on = None


def _payload_table(name: str, *key_cols: sa.Column, with_created: bool = True) -> None:
    cols = list(key_cols) + [sa.Column("payload_json", json_document_type(), nullable=False)]
    if with_created:
        cols.append(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table(name, *cols)


def upgrade() -> None:
    _payload_table(
        "risk_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
    )
    _payload_table(
        "stress_test_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
    )
    _payload_table(
        "catalysts",
        sa.Column("catalyst_id", sa.String(length=64), primary_key=True),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("catalyst_type", sa.String(length=48), nullable=False),
    )
    _payload_table(
        "catalyst_outcomes",
        sa.Column("outcome_id", sa.String(length=64), primary_key=True),
        sa.Column("catalyst_id", sa.String(length=64), nullable=False),
    )
    _payload_table(
        "performance_periods",
        sa.Column("period_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=False),
    )
    _payload_table(
        "construction_scenarios",
        sa.Column("scenario_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_type", sa.String(length=48), nullable=False),
    )
    # Market / reference data (populated when a provider is configured).
    _payload_table(
        "price_bars",
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("bar_date", sa.String(length=32), primary_key=True),
        sa.Column("interval", sa.String(length=16), primary_key=True),
        with_created=False,
    )
    _payload_table(
        "quotes",
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), primary_key=True),
        with_created=False,
    )
    _payload_table(
        "corporate_actions",
        sa.Column("action_id", sa.String(length=64), primary_key=True),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=48), nullable=False),
    )
    _payload_table(
        "estimate_points",
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("metric", sa.String(length=48), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), primary_key=True),
        with_created=False,
    )
    op.create_table(
        "application_settings",
        sa.Column("owner_id", sa.String(length=64), primary_key=True),
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value_json", json_document_type(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for name in (
        "application_settings",
        "estimate_points",
        "corporate_actions",
        "quotes",
        "price_bars",
        "construction_scenarios",
        "performance_periods",
        "catalyst_outcomes",
        "catalysts",
        "stress_test_runs",
        "risk_snapshots",
    ):
        op.drop_table(name)
