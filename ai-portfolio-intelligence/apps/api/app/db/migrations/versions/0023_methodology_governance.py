"""methodology governance tables

Revision ID: 0023_methodology_governance
Revises: 0022_fundamental_metric_lineage
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

from app.db.migration_types import (
    json_document_type,
    json_server_default_empty_array,
    json_server_default_empty_object,
    timestamp_now_default,
    uuid_column_type,
    uuid_server_default,
)

revision = "0023_methodology_governance"
down_revision = "0022_fundamental_metric_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "methodologies",
        sa.Column("methodology_id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=timestamp_now_default()),
    )
    op.create_table(
        "methodology_versions",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("methodology_id", sa.String(length=128), sa.ForeignKey("methodologies.methodology_id"), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("validator", sa.String(length=128), nullable=True),
        sa.Column("approver", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fixture_version", sa.String(length=64), nullable=True),
        sa.Column("data_version", sa.String(length=64), nullable=True),
        sa.Column(
            "tolerance_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_object(),
        ),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "known_limitations_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_array(),
        ),
        sa.Column("rollback_version", sa.String(length=32), nullable=True),
        sa.Column("supersedes_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=timestamp_now_default()),
        sa.UniqueConstraint("methodology_id", "version", name="uq_methodology_versions_identity"),
    )
    op.create_index("ix_methodology_versions_effective", "methodology_versions", ["methodology_id", "effective_at"])

    op.create_table(
        "methodology_validation_runs",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("methodology_version_id", uuid_column_type(), sa.ForeignKey("methodology_versions.id"), nullable=False),
        sa.Column("validator", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "summary_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_object(),
        ),
    )

    op.create_table(
        "methodology_validation_artifacts",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("validation_run_id", uuid_column_type(), sa.ForeignKey("methodology_validation_runs.id"), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "artifact_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_object(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=timestamp_now_default()),
    )

    op.create_table(
        "methodology_approvals",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("methodology_version_id", uuid_column_type(), sa.ForeignKey("methodology_versions.id"), nullable=False),
        sa.Column("approver", sa.String(length=128), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("methodology_approvals")
    op.drop_table("methodology_validation_artifacts")
    op.drop_table("methodology_validation_runs")
    op.drop_index("ix_methodology_versions_effective", table_name="methodology_versions")
    op.drop_table("methodology_versions")
    op.drop_table("methodologies")
