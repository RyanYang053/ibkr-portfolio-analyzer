"""Screener tables (plan §8.2 / §17).

Revision ID: 0041_screener
Revises: 0040_market_intelligence
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0041_screener"
down_revision = "0040_market_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screen_definitions",
        sa.Column("screen_id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "screen_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("screen_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "screen_results",
        sa.Column("result_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("screen_results")
    op.drop_table("screen_runs")
    op.drop_table("screen_definitions")
