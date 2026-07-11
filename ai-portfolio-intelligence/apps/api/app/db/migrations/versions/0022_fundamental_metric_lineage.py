"""fundamental metric lineage observations

Revision ID: 0022_fundamental_metric_lineage
Revises: 0021_option_contract_master
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_fundamental_metric_lineage"
down_revision = "0021_option_contract_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fundamental_metric_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("value", sa.Numeric(28, 8), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("derivation", sa.String(length=64), nullable=False),
        sa.Column("source_observation_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("calculation_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_fundamental_metric_observations_symbol_metric_asof",
        "fundamental_metric_observations",
        ["symbol", "metric", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_fundamental_metric_observations_symbol_metric_asof", table_name="fundamental_metric_observations")
    op.drop_table("fundamental_metric_observations")
