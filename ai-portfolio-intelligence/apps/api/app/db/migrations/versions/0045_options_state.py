"""Options positions/strategy/risk/scenario persistence (plan §11 / §17).

Revision ID: 0045_options_state
Revises: 0044_onboarding_state
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0045_options_state"
down_revision = "0044_onboarding_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("con_id", sa.Integer(), nullable=True),
        sa.Column("underlying", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
    )
    op.create_index("ix_option_positions_account", "option_positions", ["account_id"])

    op.create_table(
        "option_strategy_groups",
        sa.Column("group_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_type", sa.String(length=48), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "option_risk_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
    )
    op.create_index("ix_option_risk_snapshots_account", "option_risk_snapshots", ["account_id", "as_of"])

    op.create_table(
        "option_scenario_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("option_scenario_runs")
    op.drop_index("ix_option_risk_snapshots_account", table_name="option_risk_snapshots")
    op.drop_table("option_risk_snapshots")
    op.drop_table("option_strategy_groups")
    op.drop_index("ix_option_positions_account", table_name="option_positions")
    op.drop_table("option_positions")
