"""Migration 0036 — backup/restore verification and audit hash chain.

Revision ID: 0036_backup_audit_integrity
Revises: 0035_decision_calibration
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0036_backup_audit_integrity"
down_revision = "0035_decision_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("backup_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encrypted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )
    op.create_table(
        "restore_verification_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("verification_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("backup_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )
    op.create_table(
        "audit_hash_chain",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sequence", sa.Integer(), nullable=False, unique=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "provider_health_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("provider_health_events")
    op.drop_table("audit_hash_chain")
    op.drop_table("restore_verification_runs")
    op.drop_table("backup_runs")
