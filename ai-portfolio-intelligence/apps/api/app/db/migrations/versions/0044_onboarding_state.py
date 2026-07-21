"""Persisted onboarding state machine (plan §21 / §17).

Revision ID: 0044_onboarding_state
Revises: 0043_research_notes
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0044_onboarding_state"
down_revision = "0043_research_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_stages",
        sa.Column("owner_id", sa.String(length=64), primary_key=True),
        sa.Column("stage", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="not_started"),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("onboarding_stages")
