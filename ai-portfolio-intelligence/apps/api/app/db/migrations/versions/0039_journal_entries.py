"""Trade journal (plan §10 / §17).

Revision ID: 0039_journal_entries
Revises: 0038_trade_plans
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0039_journal_entries"
down_revision = "0038_trade_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("entry_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_plan_id", sa.String(length=64), nullable=True),
        sa.Column("outcome_classification", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("realized_return", sa.Float(), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journal_entries_account", "journal_entries", ["account_id"])

    op.create_table(
        "journal_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("review_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("entry_id", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("journal_reviews")
    op.drop_index("ix_journal_entries_account", table_name="journal_entries")
    op.drop_table("journal_entries")
