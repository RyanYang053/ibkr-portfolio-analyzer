"""methodology governance tables

Revision ID: 0023_methodology_governance
Revises: 0022_fundamental_metric_lineage
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "methodology_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
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
        sa.Column("tolerance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("known_limitations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rollback_version", sa.String(length=32), nullable=True),
        sa.Column("supersedes_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("methodology_id", "version", name="uq_methodology_versions_identity"),
    )
    op.create_index("ix_methodology_versions_effective", "methodology_versions", ["methodology_id", "effective_at"])

    op.create_table(
        "methodology_validation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("methodology_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("methodology_versions.id"), nullable=False),
        sa.Column("validator", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        "methodology_validation_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("validation_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("methodology_validation_runs.id"), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "methodology_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("methodology_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("methodology_versions.id"), nullable=False),
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
