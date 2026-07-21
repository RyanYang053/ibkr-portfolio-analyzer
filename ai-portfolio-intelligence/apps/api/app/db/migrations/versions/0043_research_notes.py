"""Research notes (plan §8.5 / §17).

Revision ID: 0043_research_notes
Revises: 0042_execution_matches
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0043_research_notes"
down_revision = "0042_execution_matches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_notes",
        sa.Column("note_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=True),
        sa.Column("note_type", sa.String(length=32), nullable=False, server_default="security"),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_notes_account", "research_notes", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_research_notes_account", table_name="research_notes")
    op.drop_table("research_notes")
