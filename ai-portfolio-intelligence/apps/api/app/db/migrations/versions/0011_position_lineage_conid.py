"""daily position lineage and con_id uniqueness

Revision ID: 0011_position_lineage_conid
Revises: 0010_iv_observations
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_position_lineage_conid"
down_revision = "0010_iv_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_position_snapshots", sa.Column("con_id_key", sa.Integer(), nullable=False, server_default="-1"))
    op.add_column("daily_position_snapshots", sa.Column("market_price", sa.Float()))
    op.add_column("daily_position_snapshots", sa.Column("avg_cost", sa.Float()))
    op.add_column("daily_position_snapshots", sa.Column("unrealized_pnl", sa.Float()))
    op.add_column("daily_position_snapshots", sa.Column("base_market_value", sa.Float()))
    op.add_column("daily_position_snapshots", sa.Column("fx_rate_to_base", sa.Float()))
    op.add_column("daily_position_snapshots", sa.Column("price_source", sa.String(length=64)))
    op.add_column("daily_position_snapshots", sa.Column("broker_batch_id", sa.String(length=36)))
    op.add_column("daily_position_snapshots", sa.Column("calculation_run_id", sa.String(length=64)))

    op.drop_constraint("uq_daily_position_snapshots_account_date_symbol", "daily_position_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_daily_position_snapshots_account_date_symbol",
        "daily_position_snapshots",
        ["account_id", "snapshot_date", "symbol", "con_id_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_daily_position_snapshots_account_date_symbol", "daily_position_snapshots", type_="unique")
    op.create_unique_constraint(
        "uq_daily_position_snapshots_account_date_symbol",
        "daily_position_snapshots",
        ["account_id", "snapshot_date", "symbol", "con_id"],
    )
    for column in (
        "calculation_run_id",
        "broker_batch_id",
        "price_source",
        "fx_rate_to_base",
        "base_market_value",
        "unrealized_pnl",
        "avg_cost",
        "market_price",
        "con_id_key",
    ):
        op.drop_column("daily_position_snapshots", column)
