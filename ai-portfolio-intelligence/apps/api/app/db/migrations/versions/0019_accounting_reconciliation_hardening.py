"""accounting reconciliation hardening

Revision ID: 0019_accounting_hardening
Revises: 0018_audit_event_ledger
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

from app.db.migration_types import json_document_type

revision = "0019_accounting_hardening"
down_revision = "0018_audit_event_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ledger_transactions", sa.Column("trade_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ledger_transactions", sa.Column("effective_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ledger_transactions", sa.Column("settlement_date", sa.Date(), nullable=True))
    op.add_column("ledger_transactions", sa.Column("local_symbol", sa.String(length=128), nullable=True))
    op.add_column("ledger_transactions", sa.Column("amount", sa.Numeric(24, 8), nullable=True))
    op.add_column("ledger_transactions", sa.Column("source_batch_id", sa.String(length=128), nullable=True))
    op.add_column("ledger_transactions", sa.Column("source_row_id", sa.String(length=256), nullable=True))
    op.add_column("ledger_transactions", sa.Column("source_hash", sa.String(length=64), nullable=True))

    op.add_column(
        "portfolio_snapshots",
        sa.Column("snapshot_status", sa.String(length=32), nullable=False, server_default="partial"),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column("completeness_json", json_document_type(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("portfolio_snapshots", sa.Column("valuation_coverage_percent", sa.Numeric(9, 6), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("broker_nav_tie_out", sa.Numeric(24, 8), nullable=True))
    op.add_column(
        "portfolio_snapshots",
        sa.Column("is_designated_eod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.add_column("position_snapshot_rows", sa.Column("price_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("position_snapshot_rows", sa.Column("fx_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("position_snapshot_rows", sa.Column("fx_rate_date", sa.Date(), nullable=True))
    op.add_column("position_snapshot_rows", sa.Column("source_observation_id", sa.String(length=128), nullable=True))

    op.create_index(
        "ix_portfolio_snapshots_account_date_eod",
        "portfolio_snapshots",
        ["account_id", "business_date", "is_designated_eod"],
    )
    op.create_index(
        "ix_portfolio_snapshots_account_date_status",
        "portfolio_snapshots",
        ["account_id", "business_date", "snapshot_status"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_portfolio_snapshot_designated_eod
        ON portfolio_snapshots(account_id, business_date)
        WHERE is_designated_eod = TRUE
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_portfolio_snapshot_designated_eod")
    op.drop_index("ix_portfolio_snapshots_account_date_status", table_name="portfolio_snapshots")
    op.drop_index("ix_portfolio_snapshots_account_date_eod", table_name="portfolio_snapshots")

    op.drop_column("position_snapshot_rows", "source_observation_id")
    op.drop_column("position_snapshot_rows", "fx_rate_date")
    op.drop_column("position_snapshot_rows", "fx_observed_at")
    op.drop_column("position_snapshot_rows", "price_observed_at")

    op.drop_column("portfolio_snapshots", "is_designated_eod")
    op.drop_column("portfolio_snapshots", "broker_nav_tie_out")
    op.drop_column("portfolio_snapshots", "valuation_coverage_percent")
    op.drop_column("portfolio_snapshots", "completeness_json")
    op.drop_column("portfolio_snapshots", "snapshot_status")

    op.drop_column("ledger_transactions", "source_hash")
    op.drop_column("ledger_transactions", "source_row_id")
    op.drop_column("ledger_transactions", "source_batch_id")
    op.drop_column("ledger_transactions", "amount")
    op.drop_column("ledger_transactions", "local_symbol")
    op.drop_column("ledger_transactions", "settlement_date")
    op.drop_column("ledger_transactions", "effective_timestamp")
    op.drop_column("ledger_transactions", "trade_timestamp")
