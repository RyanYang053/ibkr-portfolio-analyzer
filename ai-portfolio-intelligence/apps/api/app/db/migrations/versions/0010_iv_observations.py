"""IV observation history for percentile calculations

Revision ID: 0010_iv_observations
Revises: 0009_broker_batches_positions
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_iv_observations"
down_revision = "0009_broker_batches_positions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iv_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("implied_volatility", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "observation_date", "source", name="uq_iv_observations_symbol_date_source"),
    )
    op.create_index("ix_iv_observations_symbol_date", "iv_observations", ["symbol", "observation_date"])


def downgrade() -> None:
    op.drop_index("ix_iv_observations_symbol_date", table_name="iv_observations")
    op.drop_table("iv_observations")
