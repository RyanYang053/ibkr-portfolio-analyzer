"""Tax reconciliation minimal tables.

Revision ID: 0033_tax_reconciliation
Revises: 0032_valuation_governance
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0033_tax_reconciliation"
down_revision = "0032_valuation_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_reconciliation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tax_reconciliation_runs")
