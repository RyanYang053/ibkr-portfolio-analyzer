"""calculation run lineage for analytics outputs

Revision ID: 0008_calculation_runs
Revises: 0007_scheduler_dedup
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_calculation_runs"
down_revision = "0007_scheduler_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_type", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calculation_runs_account_created", "calculation_runs", ["account_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_calculation_runs_account_created", table_name="calculation_runs")
    op.drop_table("calculation_runs")
