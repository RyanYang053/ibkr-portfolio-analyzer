"""position snapshot lineage for reconciled accounting

Revision ID: 0016_position_snapshot_lineage
Revises: 0015_daily_position_fx_lineage
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_position_snapshot_lineage"
down_revision = "0015_daily_position_fx_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reporting_currency", sa.String(length=8), nullable=False),
        sa.Column("net_liquidation", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("settled_cash", sa.Numeric(24, 8), nullable=True),
        sa.Column("unsettled_cash", sa.Numeric(24, 8), nullable=True),
        sa.Column("accrued_interest", sa.Numeric(24, 8), nullable=True),
        sa.Column("dividend_receivable", sa.Numeric(24, 8), nullable=True),
        sa.Column("variation_margin", sa.Numeric(24, 8), nullable=True),
        sa.Column("other_accruals", sa.Numeric(24, 8), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_batch_id", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("account_id", "observed_at", name="uq_portfolio_snapshots_account_observed_at"),
    )
    op.create_index("ix_portfolio_snapshots_account_business_date", "portfolio_snapshots", ["account_id", "business_date"])

    op.create_table(
        "position_snapshot_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("portfolio_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolio_snapshots.id"), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("instrument_key", sa.String(length=256), nullable=False),
        sa.Column("con_id", sa.BigInteger(), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("local_symbol", sa.String(length=128), nullable=True),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("multiplier", sa.Numeric(20, 8), nullable=False, server_default="1"),
        sa.Column("local_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("local_market_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("fx_rate_to_base", sa.Numeric(20, 10), nullable=True),
        sa.Column("base_market_value", sa.Numeric(24, 8), nullable=True),
        sa.Column("price_source", sa.String(length=64), nullable=True),
        sa.Column("fx_source", sa.String(length=64), nullable=True),
        sa.Column("valuation_status", sa.String(length=32), nullable=False, server_default="available"),
        sa.UniqueConstraint("portfolio_snapshot_id", "instrument_key", name="uq_position_snapshot_rows_snapshot_instrument"),
    )

    op.create_table(
        "calculation_run_snapshots",
        sa.Column("calculation_run_id", sa.String(length=36), sa.ForeignKey("calculation_runs.id"), primary_key=True),
        sa.Column("portfolio_snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("portfolio_snapshots.id"), primary_key=True),
    )
    op.create_table(
        "calculation_run_transaction_batches",
        sa.Column("calculation_run_id", sa.String(length=36), sa.ForeignKey("calculation_runs.id"), primary_key=True),
        sa.Column("batch_id", sa.String(length=128), primary_key=True),
    )
    op.create_table(
        "calculation_run_market_observations",
        sa.Column("calculation_run_id", sa.String(length=36), sa.ForeignKey("calculation_runs.id"), primary_key=True),
        sa.Column("observation_id", sa.String(length=128), primary_key=True),
    )
    op.create_table(
        "calculation_run_fx_observations",
        sa.Column("calculation_run_id", sa.String(length=36), sa.ForeignKey("calculation_runs.id"), primary_key=True),
        sa.Column("observation_id", sa.String(length=128), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("calculation_run_fx_observations")
    op.drop_table("calculation_run_market_observations")
    op.drop_table("calculation_run_transaction_batches")
    op.drop_table("calculation_run_snapshots")
    op.drop_table("position_snapshot_rows")
    op.drop_index("ix_portfolio_snapshots_account_business_date", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
