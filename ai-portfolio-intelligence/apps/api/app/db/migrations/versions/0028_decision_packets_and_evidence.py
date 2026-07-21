"""Decision packets and evidence registry tables.

Revision ID: 0028_decision_packets_evidence
Revises: 0027_investor_lenses_decision
Create Date: 2026-07-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0028_decision_packets_evidence"
down_revision = "0027_investor_lenses_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evidence_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("evidence_type", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("instrument_key", sa.String(length=128), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("methodology_id", sa.String(length=128), nullable=True),
        sa.Column("methodology_version", sa.String(length=32), nullable=True),
        sa.Column("calculation_run_id", sa.String(length=64), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("provisional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("synthetic_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_evidence_records_account_instrument",
        "evidence_records",
        ["account_id", "instrument_key"],
    )

    op.create_table(
        "decision_packets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("candidate_outcome", sa.String(length=32), nullable=False),
        sa.Column("previous_outcome", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("confidence_status", sa.String(length=32), nullable=False),
        sa.Column("implementation_status", sa.String(length=32), nullable=False),
        sa.Column("packet_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_decision_packets_account_instrument_as_of",
        "decision_packets",
        ["account_id", "instrument_key", "as_of"],
    )

    op.create_table(
        "decision_gates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("gate_id", sa.String(length=64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("terminal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )
    op.create_index("ix_decision_gates_decision_id", "decision_gates", ["decision_id"])

    op.create_table(
        "decision_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("scenario_type", sa.String(length=64), nullable=False),
        sa.Column("implementation_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.UniqueConstraint("scenario_id", name="uq_decision_scenarios_scenario_id"),
    )
    op.create_index("ix_decision_scenarios_decision_id", "decision_scenarios", ["decision_id"])

    op.create_table(
        "decision_evidence_refs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="supporting"),
    )
    op.create_index("ix_decision_evidence_refs_decision_id", "decision_evidence_refs", ["decision_id"])

    op.create_table(
        "decision_changes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("change_code", sa.String(length=128), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "decision_user_responses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("response", sa.String(length=64), nullable=False),
        sa.Column("intended_weight", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=True),
    )

    op.create_table(
        "portfolio_decision_packets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_decision_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("packet_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_json", json_document_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "portfolio_decision_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_decision_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_decision_members")
    op.drop_table("portfolio_decision_packets")
    op.drop_table("decision_user_responses")
    op.drop_table("decision_changes")
    op.drop_index("ix_decision_evidence_refs_decision_id", table_name="decision_evidence_refs")
    op.drop_table("decision_evidence_refs")
    op.drop_index("ix_decision_scenarios_decision_id", table_name="decision_scenarios")
    op.drop_table("decision_scenarios")
    op.drop_index("ix_decision_gates_decision_id", table_name="decision_gates")
    op.drop_table("decision_gates")
    op.drop_index("ix_decision_packets_account_instrument_as_of", table_name="decision_packets")
    op.drop_table("decision_packets")
    op.drop_index("ix_evidence_records_account_instrument", table_name="evidence_records")
    op.drop_table("evidence_records")
