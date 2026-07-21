"""Trade Plans (plan §9 / §17).

Revision ID: 0038_trade_plans
Revises: 0037_instrument_master
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0038_trade_plans"
down_revision = "0037_instrument_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_plans",
        sa.Column("trade_plan_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("plan_type", sa.String(length=32), nullable=False, server_default="discretionary"),
        sa.Column("status", sa.String(length=48), nullable=False, server_default="draft"),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_plans_account_status", "trade_plans", ["account_id", "status"])

    op.create_table(
        "trade_plan_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trade_plan_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("trade_plan_id", "version", name="uq_trade_plan_version"),
    )


def downgrade() -> None:
    op.drop_table("trade_plan_versions")
    op.drop_index("ix_trade_plans_account_status", table_name="trade_plans")
    op.drop_table("trade_plans")
