"""Monitoring and notifications tables.

Revision ID: 0031_monitoring_notifications
Revises: 0030_research_queue
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0031_monitoring_notifications"
down_revision = "0030_research_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitoring_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=True),
        sa.Column("rule_id", sa.String(length=64), nullable=True),
        sa.Column("rule_type", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_monitoring_events_account_detected", "monitoring_events", ["account_id", "detected_at"])

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("notification_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "resolved_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("resolved_alerts")
    op.drop_table("notification_outbox")
    op.drop_index("ix_monitoring_events_account_detected", table_name="monitoring_events")
    op.drop_table("monitoring_events")
