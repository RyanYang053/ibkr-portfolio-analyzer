"""Investor lenses and decision center tables

Revision ID: 0027_investor_lenses_decision
Revises: 0026_sec_gate_audit
Create Date: 2026-07-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0027_investor_lenses_decision"
down_revision = "0026_sec_gate_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holding_theses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.UniqueConstraint("account_id", "instrument_key", name="uq_holding_theses_account_instrument"),
    )
    op.create_table(
        "holding_thesis_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("thesis_text", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.UniqueConstraint(
            "account_id",
            "instrument_key",
            "version",
            name="uq_holding_thesis_versions_account_instrument_version",
        ),
    )
    op.create_table(
        "investor_lens_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lens_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("methodology_id", sa.String(length=128), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="experimental"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lens_id", "version", name="uq_investor_lens_versions_lens_version"),
    )
    op.create_table(
        "investor_lens_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("lens_id", sa.String(length=128), nullable=False),
        sa.Column("lens_version", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_investor_lens_results_account_instrument_as_of",
        "investor_lens_results",
        ["account_id", "instrument_key", "as_of"],
    )
    op.create_table(
        "decision_simulations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "decision_monitoring_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=True),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("decision_monitoring_rules")
    op.drop_table("decision_simulations")
    op.drop_index("ix_investor_lens_results_account_instrument_as_of", table_name="investor_lens_results")
    op.drop_table("investor_lens_results")
    op.drop_table("investor_lens_versions")
    op.drop_table("holding_thesis_versions")
    op.drop_table("holding_theses")
