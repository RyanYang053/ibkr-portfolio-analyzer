"""Decision calibration observations table.

Revision ID: 0035_decision_calibration
Revises: 0034_methodology_approvals_ext
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0035_decision_calibration"
down_revision = "0034_methodology_approvals_ext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_calibration_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("user_response", sa.String(length=64), nullable=True),
        sa.Column("realized_label", sa.String(length=64), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_decision_calibration_decision_id",
        "decision_calibration_observations",
        ["decision_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_decision_calibration_decision_id", table_name="decision_calibration_observations")
    op.drop_table("decision_calibration_observations")
