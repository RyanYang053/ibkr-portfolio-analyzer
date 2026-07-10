"""financial ledger and market data persistence

Revision ID: 0002_financial_ledger
Revises: 0001_initial
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_financial_ledger"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ledger_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("transaction_id", sa.String(length=128)),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("con_id", sa.Integer()),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("commission", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("fx_rate", sa.Float()),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "transaction_id", name="uq_ledger_transactions_account_txn"),
    )
    op.create_index("ix_ledger_transactions_account_trade_date", "ledger_transactions", ["account_id", "trade_date"])

    op.create_table(
        "pnl_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("net_liquidation", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "snapshot_date", name="uq_pnl_snapshots_account_date"),
    )

    op.create_table(
        "ledger_coverage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("coverage_start", sa.Date()),
        sa.Column("coverage_end", sa.Date()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "source", name="uq_ledger_coverage_account_source"),
    )

    op.create_table(
        "fx_rate_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_currency", sa.String(length=8), nullable=False),
        sa.Column("to_currency", sa.String(length=8), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "from_currency",
            "to_currency",
            "observation_date",
            name="uq_fx_rate_observations_pair_date",
        ),
    )

    op.create_table(
        "fundamental_snapshot_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("point_in_time", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("filing_date", sa.Date()),
        sa.Column("report_period", sa.String(length=32)),
        sa.Column("synthetic_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "symbol",
            "as_of_date",
            "point_in_time",
            "source",
            "ingested_at",
            name="uq_fundamental_snapshot_records_identity",
        ),
    )


def downgrade() -> None:
    op.drop_table("fundamental_snapshot_records")
    op.drop_table("fx_rate_observations")
    op.drop_table("ledger_coverage_records")
    op.drop_table("pnl_snapshots")
    op.drop_table("ledger_transactions")
