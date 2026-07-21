"""Canonical instrument master tables (plan §17).

Revision ID: 0037_instrument_master
Revises: 0036_backup_audit_integrity
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0037_instrument_master"
down_revision = "0036_backup_audit_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.String(length=128), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("con_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("asset_class", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("is_etf", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("provisional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])

    op.create_table(
        "instrument_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("instrument_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="user"),
        sa.UniqueConstraint("alias", "instrument_id", name="uq_instrument_alias"),
    )
    op.create_index("ix_instrument_aliases_alias", "instrument_aliases", ["alias"])


def downgrade() -> None:
    op.drop_index("ix_instrument_aliases_alias", table_name="instrument_aliases")
    op.drop_table("instrument_aliases")
    op.drop_index("ix_instruments_symbol", table_name="instruments")
    op.drop_table("instruments")
