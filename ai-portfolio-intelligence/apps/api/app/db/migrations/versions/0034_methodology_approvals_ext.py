"""Methodology personal-use approvals extension.

Revision ID: 0034_methodology_approvals_ext
Revises: 0033_tax_reconciliation
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0034_methodology_approvals_ext"
down_revision = "0033_tax_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_methodology_approvals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("methodology_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("methodology_id", "version", name="uq_personal_methodology_approvals"),
    )


def downgrade() -> None:
    op.drop_table("personal_methodology_approvals")
