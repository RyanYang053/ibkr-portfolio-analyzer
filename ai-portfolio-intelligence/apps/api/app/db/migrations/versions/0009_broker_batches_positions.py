"""broker sync batches and daily position snapshots

Revision ID: 0009_broker_batches_positions
Revises: 0008_calculation_runs
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_broker_batches_positions"
down_revision = "0008_calculation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_sync_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broker_sync_batches_account_ingested", "broker_sync_batches", ["account_id", "ingested_at"])

    op.create_table(
        "daily_position_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("con_id", sa.Integer()),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id",
            "snapshot_date",
            "symbol",
            "con_id",
            name="uq_daily_position_snapshots_account_date_symbol",
        ),
    )


def downgrade() -> None:
    op.drop_table("daily_position_snapshots")
    op.drop_index("ix_broker_sync_batches_account_ingested", table_name="broker_sync_batches")
    op.drop_table("broker_sync_batches")
