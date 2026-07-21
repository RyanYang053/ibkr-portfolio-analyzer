"""Imported-execution matches (plan §9.4 / §17).

Revision ID: 0042_execution_matches
Revises: 0041_screener
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0042_execution_matches"
down_revision = "0041_screener"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_matches",
        sa.Column("match_id", sa.String(length=64), primary_key=True),
        sa.Column("trade_plan_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_matches_plan", "execution_matches", ["trade_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_execution_matches_plan", table_name="execution_matches")
    op.drop_table("execution_matches")
