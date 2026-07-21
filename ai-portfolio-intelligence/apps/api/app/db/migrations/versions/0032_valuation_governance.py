"""Valuation governance minimal tables.

Revision ID: 0032_valuation_governance
Revises: 0031_monitoring_notifications
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0032_valuation_governance"
down_revision = "0031_monitoring_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "valuation_model_approvals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.UniqueConstraint("model_id", "version", name="uq_valuation_model_approvals"),
    )


def downgrade() -> None:
    op.drop_table("valuation_model_approvals")
