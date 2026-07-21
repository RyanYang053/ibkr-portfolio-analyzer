"""Research queue tables.

Revision ID: 0030_research_queue
Revises: 0029_financial_plans_goals
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0030_research_queue"
down_revision = "0029_financial_plans_goals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_research_candidates_account_priority",
        "research_candidates",
        ["account_id", "priority"],
    )

    op.create_table(
        "research_change_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("change_code", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("research_change_events")
    op.drop_index("ix_research_candidates_account_priority", table_name="research_candidates")
    op.drop_table("research_candidates")
