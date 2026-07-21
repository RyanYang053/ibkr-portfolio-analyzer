"""Financial plans and goals tables.

Revision ID: 0029_financial_plans_goals
Revises: 0028_decision_packets_evidence
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0029_financial_plans_goals"
down_revision = "0028_decision_packets_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("owner_label", sa.String(length=128), nullable=False),
        sa.Column("base_currency", sa.String(length=16), nullable=False),
        sa.Column("planning_horizon_years", sa.Integer(), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "financial_goals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("goal_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("goal_type", sa.String(length=64), nullable=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("funded_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )
    op.create_index("ix_financial_goals_plan_id", "financial_goals", ["plan_id"])

    op.create_table(
        "investment_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("risk_tolerance", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("investment_policies")
    op.drop_index("ix_financial_goals_plan_id", table_name="financial_goals")
    op.drop_table("financial_goals")
    op.drop_table("financial_plans")
